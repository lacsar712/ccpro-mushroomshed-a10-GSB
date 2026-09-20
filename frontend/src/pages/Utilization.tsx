import { createEffect, createSignal, For, Show } from 'solid-js'
import { api } from '../api/client'
import {
  utilizationDays,
  utilizationRefreshNonce,
} from '../api/utilizationStore'
import type {
  UtilizationCheckResponse,
  UtilizationResponse,
} from '../types'

const TOLERANCE = 0.001

interface Diff {
  roomId: number
  harvestKgDiff: number
  hintDiff: number
  climateCountDiff: number
}

export default function Utilization() {
  const [data, setData] = createSignal<UtilizationResponse | null>(null)
  const [check, setCheck] = createSignal<UtilizationCheckResponse | null>(null)
  const [diffs, setDiffs] = createSignal<Diff[]>([])
  const [loading, setLoading] = createSignal(true)
  const [error, setError] = createSignal('')

  // 同时依赖侧栏天数与「新建成功」刷新信号；天数一变或新建成功立刻重拉并重对账。
  createEffect(() => {
    const days = utilizationDays()
    // 订阅刷新 nonce：新建采收/环境记录成功后自增
    utilizationRefreshNonce()
    setLoading(true)
    setError('')
    Promise.all([
      api<UtilizationResponse>(`/api/utilization?days=${days}`),
      api<UtilizationCheckResponse>(`/api/utilization-check?days=${days}`),
    ])
      .then(([main, checked]) => {
        // 前端只做两接口结果的逐室比对，绝不本地推算公斤或 hint。
        const byId = new Map(checked.perRoom.map((r) => [r.roomId, r]))
        const found: Diff[] = []
        for (const room of main.rooms) {
          const other = byId.get(room.roomId)
          if (!other) {
            found.push({
              roomId: room.roomId,
              harvestKgDiff: Number.POSITIVE_INFINITY,
              hintDiff: Number.POSITIVE_INFINITY,
              climateCountDiff: Number.POSITIVE_INFINITY,
            })
            continue
          }
          found.push({
            roomId: room.roomId,
            harvestKgDiff: Math.abs(room.harvestKg - other.harvestKg),
            hintDiff: Math.abs(room.utilizationHint - other.utilizationHint),
            climateCountDiff: Math.abs(room.climateCount - other.climateCount),
          })
        }
        setDiffs(found)
        // 对账通过才展示主接口数据
        const localOk =
          found.length === main.rooms.length &&
          found.every(
            (d) =>
              d.harvestKgDiff <= TOLERANCE &&
              d.hintDiff <= TOLERANCE &&
              d.climateCountDiff === 0
          )
        if (localOk && checked.reconciliation.passed) {
          setData(main)
          setCheck(checked)
        } else {
          setData(null)
          setCheck(checked)
          setError('对账失败：主接口与对账接口结果不一致，已阻止展示以防错误口径。')
        }
      })
      .catch((e) => {
        setData(null)
        setCheck(null)
        setError(e instanceof Error ? e.message : '加载失败')
      })
      .finally(() => setLoading(false))
  })

  const reconciled = () => data() !== null

  return (
    <div>
      <header class="page-header">
        <h1>出菇室利用率看板</h1>
        <p class="muted">
          近 {utilizationDays()} 天 · 口径：harvestKg / capacityBags；idle 强制 0；sanitize 再 ×0.5
        </p>
      </header>

      <Show when={error()}>
        <div class="error">{error()}</div>
      </Show>

      <Show when={!loading() && !reconciled() && diffs().length > 0}>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>室 ID</th>
                <th>harvestKg 差异</th>
                <th>hint 差异</th>
                <th>环境记录差异</th>
              </tr>
            </thead>
            <tbody>
              <For each={diffs()}>
                {(d) => (
                  <tr>
                    <td>{d.roomId}</td>
                    <td>{Number.isFinite(d.harvestKgDiff) ? d.harvestKgDiff.toFixed(4) : '缺失'}</td>
                    <td>{Number.isFinite(d.hintDiff) ? d.hintDiff.toFixed(4) : '缺失'}</td>
                    <td>
                      {Number.isFinite(d.climateCountDiff)
                        ? d.climateCountDiff
                        : '缺失'}
                    </td>
                  </tr>
                )}
              </For>
            </tbody>
          </table>
        </div>
      </Show>

      <Show when={check()}>
        {(c) => (
          <div
            class={`reconcile-banner ${reconciled() ? 'ok' : 'bad'}`}
          >
            <span>
              对账{reconciled() ? '通过' : '失败'} · 容差 ±{TOLERANCE} ·
              最大 harvestKg 差 {c().reconciliation.maxHarvestKgDiff} · 最大 hint 差{' '}
              {c().reconciliation.maxHintDiff} · 明细事件 {c().rows.length} 笔
            </span>
          </div>
        )}
      </Show>

      <Show when={loading()}>
        <p class="hint">对账加载中…</p>
      </Show>

      <Show when={reconciled() && data()}>
        {(main) => (
          <>
            <div class="stat-grid util-summary">
              <div class="stat-card accent">
                <div class="stat-label">纳入统计出菇室</div>
                <div class="stat-value">{main().rooms.length}</div>
              </div>
              <div class="stat-card warn">
                <div class="stat-label">窗口内采收总量 (kg)</div>
                <div class="stat-value">{main().totalHarvestKg.toFixed(2)}</div>
              </div>
              <div class="stat-card">
                <div class="stat-label">窗口内环境记录</div>
                <div class="stat-value">{main().totalClimateCount}</div>
              </div>
            </div>

            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>室 ID</th>
                    <th>编号</th>
                    <th>品种</th>
                    <th>状态</th>
                    <th>容量(袋)</th>
                    <th>采收 (kg)</th>
                    <th>环境记录</th>
                    <th>利用率 Hint</th>
                  </tr>
                </thead>
                <tbody>
                  <For each={main().rooms}>
                    {(r) => (
                      <tr>
                        <td>{r.roomId}</td>
                        <td>{r.roomCode}</td>
                        <td>{r.species}</td>
                        <td>
                          <span class={`badge ${r.status}`}>{r.status}</span>
                        </td>
                        <td>{r.capacityBags}</td>
                        <td>{r.harvestKg.toFixed(2)}</td>
                        <td>{r.climateCount}</td>
                        <td>{r.utilizationHint.toFixed(4)}</td>
                      </tr>
                    )}
                  </For>
                </tbody>
              </table>
            </div>
          </>
        )}
      </Show>
    </div>
  )
}
