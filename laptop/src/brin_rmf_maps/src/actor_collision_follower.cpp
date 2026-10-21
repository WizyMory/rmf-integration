#include <algorithm>
#include <chrono>
#include <cmath>
#include <memory>
#include <string>

#include <gz/common/Console.hh>
#include <gz/sim/Actor.hh>
#include <gz/sim/Model.hh>
#include <gz/sim/System.hh>
#include <gz/sim/components/Actor.hh>
#include <gz/sim/components/Model.hh>
#include <gz/sim/components/Name.hh>
#include <gz/plugin/Register.hh>

namespace brin_rmf_maps
{
// Fortress ignores physics links parented to actors. Drive both the actor's
// rendered trajectory and a separate static collision model from the same
// SDF waypoints, so the visible pedestrian and physical body stay aligned.
class ActorCollisionFollower final : public gz::sim::System,
                                     public gz::sim::ISystemConfigure,
                                     public gz::sim::ISystemPreUpdate
{
public:
  void Configure(const gz::sim::Entity &,
                 const std::shared_ptr<const sdf::Element> &_sdf,
                 gz::sim::EntityComponentManager &,
                 gz::sim::EventManager &) override
  {
    this->actorName = _sdf->Get<std::string>("actor_name");
    this->collisionModelName = _sdf->Get<std::string>("collision_model_name");
    this->zOffset = _sdf->Get<double>("z_offset", -1.0).first;
    ignmsg << "ActorCollisionFollower: " << this->actorName << " -> "
           << this->collisionModelName << std::endl;
  }

  void PreUpdate(const gz::sim::UpdateInfo &_info,
                 gz::sim::EntityComponentManager &_ecm) override
  {
    if (_info.paused)
      return;

    if (this->actorEntity == gz::sim::kNullEntity ||
        !gz::sim::Actor(this->actorEntity).Valid(_ecm))
    {
      this->actorEntity = gz::sim::kNullEntity;
      _ecm.Each<gz::sim::components::Actor, gz::sim::components::Name>(
          [this](const gz::sim::Entity &_entity,
                 const gz::sim::components::Actor *,
                 const gz::sim::components::Name *_name)
          {
            if (_name->Data() != this->actorName)
              return true;
            this->actorEntity = _entity;
            return false;
          });
    }
    if (this->collisionEntity == gz::sim::kNullEntity ||
        !gz::sim::Model(this->collisionEntity).Valid(_ecm))
    {
      this->collisionEntity = gz::sim::kNullEntity;
      _ecm.Each<gz::sim::components::Model, gz::sim::components::Name>(
          [this](const gz::sim::Entity &_entity,
                 const gz::sim::components::Model *,
                 const gz::sim::components::Name *_name)
          {
            if (_name->Data() != this->collisionModelName)
              return true;
            this->collisionEntity = _entity;
            return false;
          });
    }
    if (this->actorEntity == gz::sim::kNullEntity ||
        this->collisionEntity == gz::sim::kNullEntity)
      return;

    const auto *source = _ecm.Component<gz::sim::components::Actor>(
        this->actorEntity);
    if (!source || source->Data().TrajectoryCount() != 1)
      return;
    const auto &description = source->Data();
    const auto *trajectory = description.TrajectoryByIndex(0);
    if (!trajectory || trajectory->WaypointCount() < 2 ||
        !description.ScriptAutoStart())
      return;

    const double endTime = trajectory->WaypointByIndex(
        trajectory->WaypointCount() - 1)->Time();
    if (endTime <= 0.0)
      return;
    const double simTime = std::chrono::duration<double>(_info.simTime).count();
    const double delay = std::max(0.0, description.ScriptDelayStart());
    double time = simTime;
    if (description.ScriptLoop())
      time = std::fmod(time, endTime + delay);
    time = std::clamp(time - delay, 0.0, endTime);

    gz::math::Pose3d relativePose = trajectory->WaypointByIndex(0)->Pose();
    for (uint64_t i = 1; i < trajectory->WaypointCount(); ++i)
    {
      const auto *previous = trajectory->WaypointByIndex(i - 1);
      const auto *next = trajectory->WaypointByIndex(i);
      if (time > next->Time())
        continue;
      const double interval = next->Time() - previous->Time();
      const double fraction = interval > 0.0 ?
          std::clamp((time - previous->Time()) / interval, 0.0, 1.0) : 1.0;
      relativePose.Pos() = previous->Pose().Pos() * (1.0 - fraction) +
                           next->Pose().Pos() * fraction;
      relativePose.Rot() = gz::math::Quaterniond::Slerp(
          fraction, previous->Pose().Rot(), next->Pose().Rot());
      break;
    }

    gz::sim::Actor actor(this->actorEntity);
    actor.SetTrajectoryPose(_ecm, relativePose);
    actor.SetAnimationName(_ecm, trajectory->Type());
    actor.SetAnimationTime(_ecm, _info.simTime);
    auto worldPose = description.RawPose() * relativePose;
    worldPose.Pos().Z() += this->zOffset;
    gz::sim::Model(this->collisionEntity).SetWorldPoseCmd(_ecm, worldPose);
  }

private:
  std::string actorName;
  std::string collisionModelName;
  double zOffset{-1.0};
  gz::sim::Entity actorEntity{gz::sim::kNullEntity};
  gz::sim::Entity collisionEntity{gz::sim::kNullEntity};
};
}  // namespace brin_rmf_maps

IGNITION_ADD_PLUGIN(brin_rmf_maps::ActorCollisionFollower,
              gz::sim::System,
              gz::sim::ISystemConfigure,
              gz::sim::ISystemPreUpdate)
