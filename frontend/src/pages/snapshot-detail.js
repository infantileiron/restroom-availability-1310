import {download} from '../api/client.js';
import {blank, heading} from '../components/common/heading.js';
import {notify} from '../components/common/notifications.js';
import {state} from '../components/common/status.js';
import {timeAxis, track} from '../components/common/timeline.js';
import {bindAction, pollWhileActive} from '../hooks/refresh.js';
import {workspace} from '../stores/workspace.js';
import {esc} from '../utils/html.js';
import {number, percent} from '../utils/format.js';
import {go} from '../router/navigation.js';

const STATUS_TEXT = {complete: '门磁齐备', partial: '待核时段', deferred: '整日暂缓', none: '无门磁记录'};

function reconStrip(reconciliation) {
  if (!reconciliation) return '';
  const status = reconciliation.facility_status || {};
  const chips = ['complete', 'partial', 'deferred', 'none']
    .filter(key => status[key]).map(key => `<span class="status ${key}"><i></i>${STATUS_TEXT[key]} ${status[key]} 座</span>`).join('');
  return `<div class="recon-strip"><span class="recon-title">门磁对账 · ${reconciliation.policy === 'defer' ? '缺证据整日暂缓' : '缺证据先出已判明分钟'}</span>${chips}
    <span class="recon-figure">重合 <strong>${number(reconciliation.both_minutes)}</strong> 分钟 ·
    仅门磁 <strong>${number(reconciliation.door_only_minutes)}</strong> 分钟 ·
    仅登记 <strong>${number(reconciliation.outage_only_minutes)}</strong> 分钟
    ${reconciliation.pending_minutes ? ` · 待核 <strong>${number(reconciliation.pending_minutes)}</strong> 分钟` : ''}
    ${reconciliation.deferred_minutes ? ` · 整日暂缓 <strong>${number(reconciliation.deferred_minutes)}</strong> 分钟` : ''}</span></div>`;
}

function timeline(result) {
  const days = Object.keys(result.facilities[0]?.daily || {});
  if (!days.length) return '';
  const initial = days.find(day => result.facilities.some(row => row.daily[day]?.lost?.length
    || row.daily[day]?.pending?.length)) || days[0];
  return `<section class="sheet result-timeline"><div class="table-heading"><div><h2>单日核算轨道</h2>
      <div class="legend"><span><i></i>承诺开放</span><span><i class="legend-door"></i>门磁关门</span>
      <span><i class="legend-loss"></i>计入停用</span><span><i class="legend-pending"></i>待核</span></div></div>
      <label class="compact-field"><span>查看日期</span><select id="timeline-day">${days.map(day =>
        `<option ${day === initial ? 'selected' : ''} value="${day}">${day}</option>`).join('')}</select></label></div>
      <div class="report-rows" id="report-rows"></div></section>`;
}

/** @param {{facilities: import('../types/snapshot.js').FacilityResult[]}} result */
function resultBody(result) {
  const {totals, facilities, event_checks: events, reconciliation} = result;
  const siteRows = facilities.map(row => {
    const recon = row.reconciliation || {};
    const notes = [];
    if (recon.pending_minutes) notes.push(`待核 ${number(recon.pending_minutes)} 分钟`);
    if (recon.deferred_days) notes.push(`暂缓 ${number(recon.deferred_minutes)} 分钟`);
    if (recon.status === 'none') notes.push('无门磁记录，仅凭停用登记');
    if (row.incomplete_codes?.length) notes.push(`单端 ${row.incomplete_codes.join('、')}`);
    return `<tr data-code="${esc(row.code)}"><th scope="row">${esc(row.name)}<small class="mono">${esc(row.code)}</small>
      ${notes.length ? `<small class="pending-note">${esc(notes.join(' · '))}</small>` : ''}</th>
    <td class="mono">${number(row.planned_minutes)}</td><td class="mono orange">${number(row.lost_minutes)}</td>
    <td class="mono">${number(row.available_minutes)}</td>
    <td class="mono">${number(recon.both_minutes)} / ${number(recon.door_only_minutes)} / ${number(recon.outage_only_minutes)}</td>
    <td class="mono">${row.availability_pct == null ? '<span class="no-denominator">无开放分母</span>' : percent(row.availability_pct)}</td></tr>`;
  }).join('');
  const pendingTotal = (reconciliation?.pending_minutes || 0) + (reconciliation?.deferred_minutes || 0);
  return `<div class="result-grid"><div class="score"><span>全辖区开放可用率</span><strong id="district-rate">${percent(totals.availability_pct)}</strong>
    <small>${totals.excluded_facilities} 座无开放分母 / ${totals.facility_count} 座设施${pendingTotal ? ` · 待核或暂缓 ${number(pendingTotal)} 分钟未计入` : ''}</small></div>
    <dl class="result-metrics"><div><dt>已判明开放</dt><dd>${number(totals.planned_minutes)} <small>分钟</small></dd></div>
    <div><dt>有效停用</dt><dd class="orange">${number(totals.lost_minutes)} <small>分钟</small></dd></div>
    <div><dt>实际可用</dt><dd>${number(totals.available_minutes)} <small>分钟</small></dd></div></dl></div>
    ${reconStrip(reconciliation)}
    ${timeline(result)}
    <section class="sheet result-table"><div class="table-heading"><div><h2>设施月度明细</h2><p>只计承诺开放分钟 · 单位为分钟</p></div></div>
    <div class="scroll-table"><table><thead><tr><th>设施</th><th>已判明开放</th><th>有效停用</th><th>实际可用</th><th>重合 / 仅门磁 / 仅登记</th><th>可用率</th></tr></thead>
    <tbody>${siteRows}</tbody></table></div></section>
    <details class="sheet diagnostic"><summary>逐条检查记录裁剪（${events.length} 条）</summary><p>同一设施的事件可能重叠，单条裁剪结果不可直接相加；缺一端的门磁记录不进入停用分钟。</p>
    <div class="scroll-table"><table><thead><tr><th>记录编号</th><th>设施编号</th><th>落入本月</th><th>落入开放窗口</th></tr></thead><tbody>
    ${events.map(event => `<tr><th scope="row" class="mono">${esc(event.code)}</th><td class="mono">${esc(event.facility_code)}</td>
    <td>${event.in_month_minutes} 分钟</td><td>${event.inside_opening_minutes} 分钟</td></tr>`).join('')}</tbody></table></div></details>`;
}

function bindTimeline(view, result) {
  const select = view.querySelector('#timeline-day');
  if (!select) return;
  const refreshTimeline = () => {
    view.querySelector('#report-rows').innerHTML = `<div class="calendar-grid axis"><span>设施</span>${timeAxis()}</div>` +
      result.facilities.map(row => {
        const day = row.daily[select.value];
        const notes = [];
        if (day?.status === 'deferred') notes.push('整日暂缓，不计入分母');
        if (day?.pending_minutes) notes.push(`待核 ${day.pending_minutes} 分钟`);
        if (day?.both_minutes) notes.push(`重合 ${day.both_minutes} 分钟`);
        return `<div class="calendar-grid report-row"><div><strong>${esc(row.name)}</strong>
          ${notes.length ? `<small>${esc(notes.join(' · '))}</small>` : ''}</div>
        ${track({planned: day?.promised || day?.planned || [], lost: day?.lost || [],
                 door: day?.door || [], pending: day?.pending || [],
                 label: `${row.name} ${select.value} 承诺开放与停用轨道`})}</div>`;
      }).join('');
  };
  select.onchange = refreshTimeline;
  refreshTimeline();
}

export async function detailPage({view, user, active, refresh}, section, id) {
  const render = row => {
    const run = user.role === 'analyst' && ['draft', 'failed'].includes(row.status);
    const review = user.role === 'reviewer' && row.status === 'ready';
    const revise = user.role === 'analyst' && ['ready', 'published'].includes(row.status)
      ? '<button class="secondary" id="revise">补录后重算修订版</button>' : '';
    const actions = [run && '<button class="primary" id="run">执行核算</button>', revise,
      row.result && '<button class="secondary" id="export">导出 CSV</button>',
      review && '<button class="primary" id="publish">发布月报</button>'].filter(Boolean).join('');
    const computed = row.result?.computed;
    const revisionNote = row.revises
      ? `修订 V${row.revises} · 本次仅重算 ${number(computed?.recomputed_day_count ?? 0)} 个设施日，沿用 ${number(computed?.reused_days ?? 0)} 个设施日`
      : '';
    view.innerHTML = `<a class="back-link" href="#${section}">← ${section === 'reports' ? '月报清单' : '口径快照'}</a>` +
      heading(row.label, `${row.month} 月度核算 · 版本 V${row.id}${row.revision > 1 ? ` · 第 ${row.revision} 次修订` : ''}`, actions) +
      `<div class="version-strip">${state(row.status)}<span>建版 ${esc(row.created_by)}</span>
      <span class="checksum" title="${esc(row.checksum)}">SHA-256 <code>${row.checksum.slice(0, 16)}</code></span>
      ${row.published_by ? `<span>发布 ${esc(row.published_by)}</span>` : ''}
      ${revisionNote ? `<span>${revisionNote}</span>` : ''}</div>` +
      (row.result ? resultBody(row.result) : `<section class="sheet">${row.status === 'queued' ?
      blank('核算已排队', '后台将依据本版本的输入快照生成月报。') :
      blank(row.status === 'failed' ? '核算失败' : '快照已冻结', row.error || '执行核算后，可查看开放分钟、有效停用和无分母设施。')}</section>`);
    if (row.result) bindTimeline(view, row.result);
    const fail = text => notify(text, true);
    bindAction(view.querySelector('#run'), async () => { await workspace.run(id); refresh(); }, fail);
    bindAction(view.querySelector('#publish'), async () => { await workspace.publish(id); notify('月报已发布'); refresh(); }, fail);
    bindAction(view.querySelector('#export'), () => download(row), fail);
    bindAction(view.querySelector('#revise'), async () => {
      const suffix = new Date().toLocaleTimeString('zh-CN', {hour12: false});
      const base = `${row.label}·修订${suffix}`;
      const created = await workspace.revise(id, {
        month: row.month,
        label: base.slice(0, 60),
        evidence_policy: row.result?.reconciliation?.policy || 'partial',
      });
      notify(`已冻结修订版 V${created.id}，仅 ${created.affected_days} 个设施日受影响`);
      go(`${section === 'reports' ? 'runs' : section}/${created.id}`);
    }, fail);
  };
  const row = await workspace.snapshot(id);
  if (!active()) return;
  render(row);
  if (row.status === 'queued') pollWhileActive(async () => {
    try {
      const latest = await workspace.snapshot(id);
      if (active() && latest.status !== 'queued') render(latest);
      return latest.status === 'queued';
    } catch (error) {
      if (active()) notify(error.message, true);
      return active();
    }
  }, active);
}
