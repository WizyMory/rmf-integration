import { DataGrid, GridColDef } from '@mui/x-data-grid';
import { RobotDataGridTableProps } from 'react-components';
import React from 'react';
import { batteryLabel, useBatteries } from './battery-panel';

export function RobotDataGridTable({ robots, onRobotClick }: RobotDataGridTableProps) {
  const batteries = useBatteries();
  const columns: GridColDef[] = [
    { field: 'name', headerName: 'Robot', minWidth: 110, flex: 1 },
    { field: 'fleet', headerName: 'Fleet', minWidth: 110, flex: 1 },
    { field: 'level', headerName: 'Level', width: 75 },
    { field: 'battery', headerName: 'Baterai', minWidth: 220, flex: 1.6,
      valueGetter: ({ row }) => batteryLabel(batteries.find((s) => s.fleet === row.fleet && s.robot === row.name)) },
    { field: 'status', headerName: 'Status', minWidth: 110, flex: 1,
      valueGetter: ({ row }) => row.commission?.dispatch_tasks === false
        ? 'DECOMMISSIONED' : (row.status || 'unknown').toUpperCase() },
    { field: 'estFinishTime', headerName: 'Est. Task Finish', minWidth: 165, flex: 1,
      valueGetter: ({ value }) => value ? new Date(value).toLocaleString() : '—' },
    { field: 'lastUpdateTime', headerName: 'Last Updated', minWidth: 165, flex: 1,
      valueGetter: ({ value }) => value ? new Date(value).toLocaleString() : '—' },
  ];
  return <DataGrid autoHeight rows={robots} columns={columns} pageSize={5} rowsPerPageOptions={[5]}
    getRowId={(r) => JSON.stringify([r.fleet, r.name])} rowHeight={42}
    onRowClick={(params, event) => onRobotClick?.(event, params.row)}
    initialState={{ sorting: { sortModel: [{ field: 'name', sort: 'asc' }] } }} />;
}
