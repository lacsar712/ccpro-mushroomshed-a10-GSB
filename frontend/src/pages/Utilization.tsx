import { createSignal, onMount, For, Show } from 'solid-js'
import { api } from '../api/client'
import type { Room, UtilizationBoard, UtilizationCheck } from '../types'

// 与后端 app/services/utilization.py RECONCILE_TOLERANCE 一致
const TOLERANCE = 0.001
const DAY_PRESETS = [7, 14, 30]

const STATUS_LABELS: Record<string, string> = {
  fruiting: '出菇中',
  idle: '闲置',
  sanitize: '消毒中',
}

export default function Utilization() {
  const [days, setDays] = createSignal(7)
  const [roomId, setRoomId] = createSignal('')
  const [rooms, setRooms] = createSignal<Room[]>([])
  const [board, setBoard] = createSignal<UtilizationBoard | null>(null)
  const [reconciled, setReconciled] = createSignal(false)
  const [checkedRooms, setCheckedRooms] = createSignal(0)
  const [error, setError] = createSignal('')
  const [loading, setLoading] = createSignal(false)

  async function load() {
    setLoading(true)
    setError('')
    setReconciled(false)
    setBoard(null)
    try {
      // 同一个 asOf 钉住窗口右端，两次请求筛选完全一致
      const params = new URLSearchParams({
        days: String(days()),
        asOf: new Date().toISOString(),
      })
      if (roomId()) params.set('roomId', roomId())
      const qs = params.toString()
      const [main, check] = await Promise.all([
        api<UtilizationBoard>(`/api/utilization?${qs}`),
        api<UtilizationCheck>(`/api/utilization-check?${qs}`),
      ])

      // 先对账再展示：逐室 |ΔharvestKg|、|Δhint| 必须 ≤ 0.001
      const problems: string[] = []
      if (main.rooms.length !== check.rows.length) {
        problems.push(`行数不一致（主 ${main.rooms.length} / 对账 ${check.rows.length}）`)
      }
      for (const r of main.rooms) {
        const ref = check.perRoom[String(r.roomId)]
        if (!ref) {
          problems.push(`室 ${r.roomCode} 在对账接口缺失`)
          continue
        }
        const dKg = Math.abs(ref.harvestKg - r.harvestKg)
        const dHint = Math.abs(ref.utilizationHint - r.utilizationHint)
        if (dKg > TOLERANCE || dHint > TOLERANCE) {
          problems.push(
            `室 ${r.roomCode} 超差：Δkg=${dKg.toFixed(6)}，Δhint=${dHint.toFixed(6)}`,
          )
        }
      }
      if (problems.length > 0) {
        setError(`对账失败，已拒绝展示：${problems.join('；')}`)
        return
      }
      setBoard(main)
      setCheckedRooms(main.rooms.length)
      setReconciled(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }

  onMount(() => {
    api<Room[]>('/api/rooms')
      .then(setRooms)
      .catch(() => {})
    load()
  })

  function pickDays(d: number) {
    setDays(d)
    load()
  }

  function onCustomDays(e: Event) {
    const v = Number((e.currentTarget as HTMLInputElement).value)
    if (Number.isInteger(v) && v >= 1 && v <= 90) {
      setDays(v)
      load()
    }
  }

  const totalKg = () =>
    (board()?.rooms ?? []).reduce((sum, r) => sum + r.harvestKg, 0)
  const totalClimate = () =>
    (board()?.rooms ?? []).reduce((sum, r) => sum + r.climateCount, 0)

  return (
    <div>
      <header class="page-header">
        <h1>出菇室利用率</h1>
        <p class="muted">
          hint = 采收kg ÷ (容量袋数 × 天数)；idle 强制 0；sanitize 按公式 × 0.5
        </p>
      </header>

      {error() && <div class="error">{error()}</div>}

      <div class="util-layout">
        <aside class="panel util-side">
          <div class="util-side-title">统计口径</div>
          <label>
            天数（1–90）
            <div class="day-presets">
              <For each={DAY_PRESETS}>
                {(d) => (
                  <button
                    type="button"
                    class={`day-btn${days() === d ? ' active' : ''}`}
                    onClick={() => pickDays(d)}
                  >
                    {d} 天
                  </button>
                )}
              </For>
            </div>
            <input
              type="number"
              min="1"
              max="90"
              value={days()}
              onInput={onCustomDays}
            />
          </label>
          <label>
            出菇室
            <select
              value={roomId()}
              onChange={(e) => {
                setRoomId(e.currentTarget.value)
                load()
              }}
            >
              <option value="">全部出菇室</option>
              <For each={rooms()}>
                {(r) => (
                  <option value={String(r.id)}>
                    {r.roomCode} · {r.species}
                  </option>
                )}
              </For>
            </select>
          </label>
          <button type="button" class="btn ghost" onClick={() => load()}>
            刷新并对账
          </button>
          <p class="hint">
            每次加载先调用 /api/utilization-check 对账，逐室误差 ≤ 0.001 才展示。
          </p>
        </aside>

        <section>
          <Show when={reconciled()}>
            <div class="reconcile-ok">
              对账通过 · {checkedRooms()} 室 · 容差 ≤ {TOLERANCE} · 窗口右端{' '}
              {board() ? new Date(board()!.asOf).toLocaleString() : ''}
            </div>
          </Show>
          {loading() && <p class="muted">加载并对账中…</p>}

          <Show when={reconciled() && board()}>
            <div class="stat-grid util-stats">
              <div class="stat-card">
                <div class="stat-label">统计室数</div>
                <div class="stat-value">{board()!.rooms.length}</div>
              </div>
              <div class="stat-card accent">
                <div class="stat-label">合计采收 (kg)</div>
                <div class="stat-value">{totalKg().toFixed(3)}</div>
              </div>
              <div class="stat-card">
                <div class="stat-label">环境记录总数</div>
                <div class="stat-value">{totalClimate()}</div>
              </div>
            </div>

            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>室编号</th>
                    <th>品种</th>
                    <th>状态</th>
                    <th>容量(袋)</th>
                    <th>采收 kg</th>
                    <th>环境记录</th>
                    <th>利用率 hint</th>
                  </tr>
                </thead>
                <tbody>
                  <For each={board()!.rooms}>
                    {(r) => (
                      <tr>
                        <td>{r.roomCode}</td>
                        <td>{r.species}</td>
                        <td>
                          <span class={`badge ${r.status}`}>
                            {STATUS_LABELS[r.status] ?? r.status}
                          </span>
                        </td>
                        <td>{r.capacityBags}</td>
                        <td>{r.harvestKg.toFixed(3)}</td>
                        <td>{r.climateCount}</td>
                        <td>{r.utilizationHint.toFixed(6)}</td>
                      </tr>
                    )}
                  </For>
                </tbody>
              </table>
            </div>
          </Show>
        </section>
      </div>
    </div>
  )
}
