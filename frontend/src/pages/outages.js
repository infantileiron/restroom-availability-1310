import {REASONS} from '../constants/business.js';
import {workspace} from '../stores/workspace.js';
import {blank, heading} from '../components/common/heading.js';
import {edit, field} from '../components/common/editor.js';
import {notify} from '../components/common/notifications.js';
import {reason} from '../components/common/status.js';
import {esc, formValues} from '../utils/html.js';
import {localStamp} from '../utils/format.js';

function doorRows(rows, names) {
  const shown = rows;
  if (!shown.length) return blank('暂无门磁记录', '导入门磁开关 CSV 后，这里会列出开关门时间。');
  return `<div class="scroll-table"><table><thead><tr><th>记录编号 / 设施</th><th>关门</th><th>开门</th>
    <th>证据</th><th>备注</th></tr></thead><tbody>${shown.map(row => {
    const complete = row.closed_at && row.reopened_at;
    return `<tr><th scope="row"><strong>${esc(names[row.facility_code] || row.facility_code)}</strong>
      <small class="mono">${esc(row.code)}</small></th>
      <td class="mono nowrap">${row.closed_at ? localStamp(row.closed_at) : '<span class="missing">缺</span>'}</td>
      <td class="mono nowrap">${row.reopened_at ? localStamp(row.reopened_at) : '<span class="missing">缺</span>'}</td>
      <td>${complete ? '<span class="status complete"><i></i>成对</span>' : '<span class="status partial"><i></i>单端待核</span>'}</td>
      <td>${esc(row.note)}</td></tr>`;
  }).join('')}</tbody></table></div>`;
}

export async function outagesPage({view, user, active, refresh}) {
  const [sites, rows, doors, imports] = await Promise.all([
    workspace.facilities(), workspace.outages(), workspace.doorRecords(), workspace.doorImports()]);
  if (!active()) return;
  const names = Object.fromEntries(sites.map(site => [site.code, site.name]));
  const siteOptions = sites.map(site => `<option value="${esc(site.code)}">${esc(site.name)}</option>`).join('');
  const analyst = user.role === 'analyst';
  const latest = imports[0];
  view.innerHTML = heading('停用核对', '登记停水与设备故障，并用门磁开关记录核对实际停用分钟。',
    analyst ? '<button class="secondary" id="import-door">导入门磁记录</button><button class="primary" id="new-outage">登记停用</button>' : '') +
    `<section class="sheet"><div class="table-heading"><div><h2>停用登记</h2><p id="outage-count"></p></div>
    <label class="compact-field"><span>设施</span><select id="site-filter"><option value="">全部设施</option>${siteOptions}</select></label></div>
    <div id="outage-table"></div></section>
    <section class="sheet door-sheet"><div class="table-heading"><div><h2>门磁开关记录</h2>
    <p id="door-count">${latest ? `最近导入 ${esc(latest.filename)} · ${latest.row_count} 行 · ${esc(localStamp(latest.imported_at))}` : '尚未导入门磁记录'}</p></div>
    <label class="compact-field"><span>设施</span><select id="door-filter"><option value="">全部设施</option>${siteOptions}</select></label></div>
    <div id="door-table"></div></section>
    <aside class="note"><strong>证据要求</strong><span>只有关门和开门成对的门磁记录才能证明停用。缺一端时，当天未能判明的时间在月报中列为待核；停用登记与门磁记录重合的部分只计一次。</span></aside>`;
  const filter = view.querySelector('#site-filter');
  const renderRows = () => {
    const shown = rows.filter(row => !filter.value || row.facility_code === filter.value);
    view.querySelector('#outage-count').textContent = `${shown.length} 条记录 · 现场上报时间`;
    view.querySelector('#outage-table').innerHTML = !shown.length ? blank('暂无停用记录', '更换设施筛选，或登记新的停用记录。') :
      `<div class="scroll-table"><table><thead><tr><th>记录编号 / 设施</th><th>停用原因</th><th>开始</th><th>恢复</th><th>巡维备注</th></tr></thead>
      <tbody>${shown.map(row => `<tr><th scope="row"><strong>${esc(names[row.facility_code])}</strong><small class="mono">${esc(row.code)}</small></th>
      <td>${reason(row.reason)}</td><td class="mono nowrap">${localStamp(row.starts_at)}</td><td class="mono nowrap">${localStamp(row.ends_at)}</td>
      <td>${esc(row.note)}</td></tr>`).join('')}</tbody></table></div>`;
  };
  const doorFilter = view.querySelector('#door-filter');
  const renderDoors = () => {
    const shown = doors.filter(row => !doorFilter.value || row.facility_code === doorFilter.value);
    view.querySelector('#door-count').textContent = shown.length ?
      `${shown.length} 条记录 · ${latest ? `最近导入 ${latest.filename}` : '演示数据'}` : '尚未导入门磁记录';
    view.querySelector('#door-table').innerHTML = doorRows(shown, names);
  };
  filter.onchange = renderRows;
  doorFilter.onchange = renderDoors;
  renderRows();
  renderDoors();
  if (!analyst) return;

  const button = view.querySelector('#new-outage');
  button.disabled = !sites.length;
  button.onclick = () => edit('登记停用',
    `<div class="form-grid">${field('记录编号', '<input name="code" required maxlength="24" pattern="[A-Z0-9][A-Z0-9\\-]{1,23}" placeholder="例 WX-1109">')}
    ${field('设施', `<select name="facility_code">${siteOptions}</select>`)}</div>
    ${field('停用原因', `<select name="reason">${Object.entries(REASONS).map(([code, label]) => `<option value="${code}">${label}</option>`).join('')}</select>`)}
    <div class="form-grid">${field('停用开始', '<input name="starts_at" type="datetime-local" required>')}
    ${field('恢复时间', '<input name="ends_at" type="datetime-local" required>')}</div>
    ${field('巡维备注', '<textarea name="note" maxlength="240" required rows="2"></textarea>')}`, async form => {
      await workspace.createOutage(formValues(form));
      return () => { notify('停用记录已登记'); refresh(); };
    });

  const importer = view.querySelector('#import-door');
  importer.onclick = () => edit('导入门磁记录',
    `<label class="field"><span>门磁开关 CSV</span><input name="file" type="file" accept=".csv,text/csv" required></label>
     <p class="field-note">列名支持：记录编号、设施编号、关门时间、开门时间、备注。缺一端时间的行会保留为待核证据，不会当作已开关。</p>`,
    async form => {
      const file = form.querySelector('input[type=file]').files[0];
      if (!file) throw new Error('请选择门磁记录 CSV 文件');
      const result = await workspace.importDoorRecords(file);
      return () => {
        notify(`已导入 ${result.created} 条新记录，补全 ${result.updated} 条${result.incomplete ? `，${result.incomplete} 条单端待核` : ''}`);
        refresh();
      };
    });
}
