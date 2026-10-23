/**
 * Spoken 「要发财啦」 when the workbench alert consoles gain or change a line.
 * The first click or key unlocks audio. One burst of updates speaks once.
 */

import { ALERT_UI, FORTUNE_CHIME_DEBOUNCE_MS, pickFortuneVoice, shouldPlayChime } from './workbenchAlerts'

const FORTUNE_PITCH = 1.8
const FORTUNE_RATE = 1.05

let unlocked = false
let lastPlayedAt = 0

function speakFortune() {
  const synth = window.speechSynthesis
  if (!synth) return
  const utter = new SpeechSynthesisUtterance(ALERT_UI.fortune)
  utter.lang = 'zh-CN'
  utter.pitch = FORTUNE_PITCH
  utter.rate = FORTUNE_RATE
  const voice = pickFortuneVoice(synth.getVoices())
  if (voice) utter.voice = voice
  synth.speak(utter)
}

/** Ask for a chime. Locked browsers and a second call inside the debounce window stay quiet. */
export function noteWorkbenchAlertChime() {
  if (typeof window === 'undefined' || !unlocked) return
  const now = Date.now()
  if (!shouldPlayChime(lastPlayedAt, now, FORTUNE_CHIME_DEBOUNCE_MS)) return
  lastPlayedAt = now
  speakFortune()
}

function unlock() {
  if (unlocked || typeof window === 'undefined') return
  unlocked = true
  const synth = window.speechSynthesis
  if (!synth) return
  try {
    synth.resume()
    const warm = new SpeechSynthesisUtterance(' ')
    warm.volume = 0
    warm.lang = 'zh-CN'
    synth.speak(warm)
  } catch {
    // The gesture still unlocks later alert updates.
  }
}

if (typeof window !== 'undefined') {
  window.addEventListener('pointerdown', unlock, { capture: true })
  window.addEventListener('keydown', unlock, { capture: true })
  window.speechSynthesis?.addEventListener?.('voiceschanged', () => {
    window.speechSynthesis.getVoices()
  })
}
