import {api} from '../api/client.js';

export const workspace = {
  facilities: () => api('/facilities'),
  outages: () => api('/outages'),
  doorRecords: (month = '') => api(`/door-records${month ? `?month=${encodeURIComponent(month)}` : ''}`),
  doorImports: () => api('/door-imports'),
  snapshots: () => api('/snapshots'),
  snapshot: id => api(`/snapshots/${id}`),
  createFacility: input => api('/facilities', input),
  addWindow: (code, input) => api(`/facilities/${code}/windows`, input),
  createOutage: input => api('/outages', input),
  importDoorRecords: file => {
    const body = new FormData();
    body.append('file', file);
    return api('/door-records/import', body, false, true);
  },
  publish: id => api(`/snapshots/${id}/publish`, {}),
  capture: input => api('/snapshots', input),
  revise: (id, input) => api('/snapshots', {...input, revises: id}),
  run: id => api(`/snapshots/${id}/run`, {}),
};
