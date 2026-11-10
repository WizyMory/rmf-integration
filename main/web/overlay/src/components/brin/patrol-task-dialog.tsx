import { Alert, Autocomplete, Button, Dialog, DialogActions, DialogContent, DialogTitle,
  MenuItem, Stack, TextField, Typography } from '@mui/material';
import React from 'react';
import { RmfAppContext } from '../rmf-app';
import { AppEvents } from '../app-events';
import { makePatrolRequest, RobotChoice, submitPatrol } from './patrol-request';

interface Props {
  waypoints: string[];
  user: string;
  onClose: () => void;
  onAdvanced: () => void;
  onSuccess: () => void;
}

export function PatrolTaskDialog({ waypoints, user, onClose, onAdvanced, onSuccess }: Props) {
  const rmf = React.useContext(RmfAppContext);
  const [places, setPlaces] = React.useState<string[]>([]);
  const [rounds, setRounds] = React.useState(1);
  const [robotKey, setRobotKey] = React.useState('auto');
  const [robots, setRobots] = React.useState<RobotChoice[]>([]);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState('');
  const [loaded, setLoaded] = React.useState(false);
  const options = React.useMemo(() => Array.from(new Set(waypoints.filter((p) => p.trim()))).sort(), [waypoints]);
  React.useEffect(() => {
    if (!rmf) return;
    let active = true;
    const refresh = async () => {
      try {
        const response = await rmf.fleetsApi.getFleetsFleetsGet();
        const choices = response.data.flatMap((fleet) => Object.entries(fleet.robots || {}).map(([robot, state]) => ({
          fleet: fleet.name || '', robot,
          disabled: !state.unix_millis_time || Date.now() - state.unix_millis_time > 15000
            || ['offline', 'shutdown', 'uninitialized', 'error'].includes(state.status || ''),
        })));
        if (active) { setRobots(choices); setLoaded(true); }
      } catch (_) {
        if (active) { setRobots([]); setLoaded(false); }
      }
    };
    refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => { active = false; window.clearInterval(timer); };
  }, [rmf]);
  const robot = robots.find((r) => JSON.stringify([r.fleet, r.robot]) === robotKey);
  const valid = places.length > 0 && places.every((p) => options.includes(p))
    && Number.isInteger(rounds) && rounds >= 1 && rounds <= 100
    && loaded && robots.some((r) => !r.disabled)
    && (robotKey === 'auto' || (robot && !robot.disabled));

  const submit = async () => {
    if (!rmf || !valid || busy) return;
    setBusy(true); setError('');
    try {
      await submitPatrol(rmf.tasksApi, makePatrolRequest(places, rounds, user), robotKey === 'auto' ? null : robot!);
      AppEvents.refreshTaskApp.next(); onSuccess();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open onClose={busy ? undefined : onClose} fullWidth maxWidth="sm">
      <DialogTitle>New Task · Patrol</DialogTitle>
      <DialogContent>
        <Stack spacing={3} sx={{ pt: 1 }}>
          <Typography variant="body2" color="text.secondary">Pilih waypoint, lalu kirim task. Robot dipilih otomatis melalui bidding RMF atau tentukan robot sendiri.</Typography>
          <Autocomplete multiple options={options} value={places} disabled={busy}
            onChange={(_, value) => setPlaces(value)}
            renderInput={(params) => <TextField {...params} label="Waypoint tujuan" placeholder="Cari waypoint"
              helperText={options.length ? 'Robot mengunjungi waypoint sesuai urutan pilihan.' : 'Menunggu waypoint dari peta RMF…'} />} />
          <TextField select label="Robot pelaksana" value={robotKey} disabled={busy}
            onChange={(e) => setRobotKey(e.target.value)}>
            <MenuItem value="auto">Otomatis · bidding RMF</MenuItem>
            {robots.map((r) => <MenuItem key={JSON.stringify([r.fleet, r.robot])}
              value={JSON.stringify([r.fleet, r.robot])} disabled={r.disabled}>
              {r.fleet} / {r.robot}{r.disabled ? ' · tidak tersedia' : ''}
            </MenuItem>)}
          </TextField>
          <TextField type="number" label="Jumlah putaran" value={rounds} disabled={busy}
            inputProps={{ min: 1, max: 100, step: 1 }} onChange={(e) => setRounds(Number(e.target.value))} />
          {(!loaded || !robots.some((r) => !r.disabled)) && <Alert severity="info">Menunggu robot terhubung ke RMF.</Alert>}
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ p: 2 }}>
        <Button onClick={onAdvanced} disabled={busy}>Opsi lanjutan</Button>
        <Button onClick={onClose} disabled={busy}>Batal</Button>
        <Button variant="contained" onClick={submit} disabled={!valid || busy}>{busy ? 'Mengirim…' : 'Kirim Patrol'}</Button>
      </DialogActions>
    </Dialog>
  );
}
