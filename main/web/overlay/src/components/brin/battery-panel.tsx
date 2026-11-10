import { BatteryFull, BatteryUnknown } from '@mui/icons-material';
import { Box, Chip, Stack, Tooltip, Typography } from '@mui/material';
import React from 'react';

export interface BatterySample {
  fleet: string;
  robot: string;
  soc: number | null;
  voltage: number | null;
  estimated: boolean;
  stale: boolean;
  source: string;
  age_seconds: number | null;
}

export function useBatteries() {
  const [samples, setSamples] = React.useState<BatterySample[]>([]);
  React.useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const refresh = async () => {
      try {
        const response = await fetch('/brin/batteries', {
          cache: 'no-store', signal: controller.signal,
        });
        if (!response.ok) throw new Error('Battery telemetry unavailable');
        const data = await response.json();
        if (active) setSamples(Array.isArray(data.robots) ? data.robots : []);
      } catch (_) {
        if (active) setSamples([]);
      }
    };
    refresh();
    const timer = window.setInterval(refresh, 3000);
    return () => { active = false; controller.abort(); window.clearInterval(timer); };
  }, []);
  return samples;
}

export function batteryLabel(sample: BatterySample | undefined): string {
  if (!sample || sample.stale) return 'Data baterai belum tersedia';
  const soc = sample.soc == null ? 'SOC tidak tersedia' : `${Math.round(sample.soc * 100)}%`;
  const voltage = sample.voltage == null ? '' : ` · ${sample.voltage.toFixed(2)} V`;
  return `${sample.estimated ? '≈ ' : ''}${soc}${voltage}`;
}

export function RobotBatteryPanel() {
  const samples = useBatteries();
  const expected = [
    { fleet: 'HuskyA200', robot: 'husky_0', label: 'Husky' },
    { fleet: 'Devi', robot: 'devi', label: 'Devi' },
  ];
  return (
    <Stack direction="row" spacing={2} alignItems="center" sx={{ px: 2, py: 1, flexWrap: 'wrap', gap: 1 }}>
      <Typography variant="body2" color="text.secondary">Baterai robot</Typography>
      {expected.map((robot) => {
        const sample = samples.find((s) => s.fleet === robot.fleet && s.robot === robot.robot);
        const available = !!sample && !sample.stale && sample.soc != null;
        return (
          <Tooltip key={robot.fleet} title={sample?.estimated
            ? 'Estimasi tegangan Devi: 15 V = 0%, 25 V = 100%'
            : 'SOC dari BMS Husky'}>
            <Box component="span">
              <Chip variant="outlined" icon={available ? <BatteryFull /> : <BatteryUnknown />}
                color={available && sample!.soc! < 0.2 ? 'warning' : 'default'}
                label={`${robot.label}: ${batteryLabel(sample)}`} />
            </Box>
          </Tooltip>
        );
      })}
    </Stack>
  );
}
