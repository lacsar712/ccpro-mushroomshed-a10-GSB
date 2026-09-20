import { createSignal } from 'solid-js'

// 侧栏天数切换与利用率看板共享；所有公斤/hint 均来自后端，前端不本地推算。
const DAY_OPTIONS = [1, 7, 14, 30] as const
const DEFAULT_DAYS = 7

const [days, setDays] = createSignal<number>(DEFAULT_DAYS)
// 每次「新建采收 / 环境记录」成功后自增，看板据此立刻重新拉取并对账。
const [refreshNonce, bumpRefresh] = createSignal(0)

export function utilizationDays() {
  return days()
}

export function setUtilizationDays(value: number) {
  if (DAY_OPTIONS.includes(value as (typeof DAY_OPTIONS)[number])) {
    setDays(value)
  }
}

export function utilizationRefreshNonce() {
  return refreshNonce()
}

export function notifyUtilizationDataChanged() {
  bumpRefresh((n) => n + 1)
}

export { DAY_OPTIONS, DEFAULT_DAYS }
