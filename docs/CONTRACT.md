# Контракт: протокол и uniform'ы

Единый источник правды между бэком, фронтом и агентами. Этот же файл (как `docs/CONTRACT.md`) передаётся шейдер-агентам в промпте. Любое изменение — явно, с перечнем того, что поправить в бэке, фронте и промптах.

Статус: **черновик v0** — поля могут уточняться на первом этапе.

## 1. FeatureFrame (бэк → фронт, 60 Гц)

```python
@dataclass
class FeatureFrame:
    t: float                 # время движка, с
    bands: list[float]       # 64 лог-полосы 30 Гц–16 кГц, 0..1, сглаженные (attack/release)
    waveform: list[float]    # 512 точек, даунсэмпл, -1..1
    peaks: list[tuple[float, float, float]]  # top-8: (freq_hz, amp 0..1, phase рад) — для слоя Фурье
    kick: float              # огибающая кика 0..1 (мгновенная атака, эксп. спад)
    bass: float              # 0..1
    mid: float               # 0..1
    high: float              # 0..1
    bpm: float
    beat_phase: float        # 0..1 внутри доли
    bar: int                 # номер такта
    beat_in_bar: int         # 0..3
    energy: float            # медленная энергия (~4 такта), 0..1
```

Сериализация: **msgpack** (или сырой float32-буфер). JSON на 60 Гц не использовать.

Для будущего веб-демо без бэкенда тот же фрейм можно собрать в браузере через `AnalyserNode` — фронту всё равно, откуда пришли фичи.

## 2. Uniform'ы шейдеров (обязательный блок)

Каждый шейдер сцены (GLSL ES 3.0, WebGL2, фрагментный) обязан объявить и использовать только эти входы:

```glsl
#version 300 es
precision highp float;

uniform float u_time;        // секунды (может замедляться модулятором)
uniform float u_kick;        // 0..1
uniform float u_bass;        // 0..1
uniform float u_mid;         // 0..1
uniform float u_high;        // 0..1
uniform float u_bpm;
uniform float u_beat_phase;  // 0..1
uniform float u_energy;      // 0..1
uniform float u_intensity;   // 0..1, от режиссёра/модулятора
uniform vec3  u_palette[3];  // палитра сцены
uniform sampler2D u_spectrum;// 64x1, R = bands[i]
uniform sampler2D u_prev;    // предыдущий кадр (feedback/шлейф)
uniform vec2  u_resolution;

out vec4 fragColor;
```

Ограничения для агентов: без внешних текстур кроме перечисленных, без циклов с неконстантной границей больше ~64 итераций, целевые 60 fps на встроенной графике ноутбука.

## 3. Control-сообщения (бэк → фронт)

```jsonc
{ "type": "shader.load",  "id": "concrete_strobe", "code": "<glsl>" }
{ "type": "scene.switch", "id": "concrete_strobe", "transition_bars": 2 }
{ "type": "scene.params", "intensity": 0.8, "palette": ["#0D0D0D", "#EC6D1C", "#EDEAE4"] }
{ "type": "director.log", "bar": 80, "text": "дроп → кроссфейд в «бетон», 2 такта" }
{ "type": "decks.state",  "decks": [ /* DeckState, см. 04 */ ], "crossfader": 0.37 }
{ "type": "studio.progress", "order_id": "...", "for_deck": "B", "progress": 0.6 }
```

Control-сообщения редкие, их можно слать JSON.

## 4. Ответы фронта (фронт → бэк)

```jsonc
{ "type": "shader.compiled", "id": "concrete_strobe", "ok": true }
{ "type": "shader.compiled", "id": "concrete_strobe", "ok": false, "error": "ERROR: 0:14: ..." }
{ "type": "frame.capture",   "id": "concrete_strobe", "state": "kick_peak", "png_b64": "..." } // для критика
{ "type": "prompt",          "text": "холодно, бетон, стробы на кик" }
```

## 5. Выход режиссёра (structured output)

```json
{ "scene": "concrete_strobe", "palette": "amber", "intensity": 0.8, "transition_bars": 2,
  "order": { "brief": "туман, медленно, низкий контраст", "for_deck": "B", "deadline_bars": 16 } }
```

`order` — необязательный заказ сцены в студию (prefetch).
