# Crop Preview — Zoom Loupe Design

**Date:** 2026-04-13
**Status:** Approved
**Scope:** `app-v2/components/CropOverlay.tsx` + new `app-v2/utils/loupeMath.ts`

---

## Problem

When a user drags a quad corner handle on the crop preview screen, their thumb (56pt hit target) completely covers the 14pt visible corner circle. There is no way to see precisely where the corner is placed during the drag. This makes fine adjustment of the crop quad difficult on a physical device.

---

## Solution

Show a floating magnifier loupe above the active corner while dragging. The loupe displays a 2.5× zoomed view of the image centred exactly on the corner position, with a crosshair marking the precise placement. It appears on drag start and disappears on drag end.

---

## Visual Design

- **Shape:** 110pt diameter circle with `overflow: hidden` for circular clip
- **Zoom:** 2.5×
- **Default position:** 75pt above the active corner, horizontally centred on it
- **Edge flip:** When the corner is within 120pt of the top of the image frame (`activeCY - offsetY < 120`), the loupe appears 40pt below the corner instead of above
- **Tether:** A short dashed line (`#89C7FE`, 3pt dash / 2.5pt gap, 45% opacity) connects the bottom (or top, when flipped) of the loupe to the corner position
- **Crosshair:** Two 20pt lines + 2.5pt dot at the loupe centre, `#89C7FE` at 70% opacity — marks the exact corner pixel
- **Visibility:** `opacity` animated 0 → 1 on drag start, 1 → 0 on drag end (no fade delay; instant)
- **Hint text:** Fades to 10% opacity while any drag is in progress (the loupe replaces its purpose)

---

## Architecture

### Option chosen: Inline in CropOverlay

All loupe state lives inside `CropOverlay`. No changes to `crop-preview.tsx`. The only new public surface is one additional prop on `CropOverlay`.

### Component changes

**`CropOverlay` (`components/CropOverlay.tsx`)**

New prop:
```ts
imageUri: string
```

New internal shared values:
```ts
const activeCX = useSharedValue(0)
const activeCY = useSharedValue(0)
const isDragging = useSharedValue(0) // 0 | 1
```

`CornerHandle` receives a new `onDragActive` worklet prop:
```ts
onDragActive: (cx: number, cy: number) => void
onDragEnd: () => void  // already exists — extended to reset isDragging
```

On `onStart`: set `isDragging.value = 1` (UI thread, direct assignment)
On `onUpdate`: call `onDragActive(cx.value, cy.value)` directly — gesture callbacks run on the UI thread in Reanimated 3; `onDragActive` must be a worklet function
On `onEnd`: set `isDragging.value = 0`, then call `runOnJS(onDragEnd)()` (already present)

**`LoupeView` (sub-component, defined in `CropOverlay.tsx`)**

A new internal component rendered inside `CropOverlay` as a sibling to `<Svg>`:

```ts
interface LoupeViewProps {
  imageUri: string
  activeCX: SharedValue<number>
  activeCY: SharedValue<number>
  isDragging: SharedValue<number>
  containerWidth: number
  containerHeight: number
  offsetX: number
  offsetY: number
  frameW: number
  frameH: number
}
```

Renders:
1. `Animated.View` (outer — position + opacity)
2. `Animated.View` (inner — `width: 110, height: 110, borderRadius: 55, overflow: 'hidden'`)
3. `<Image>` inside inner view (zoomed image, translated to centre the corner)
4. `<Svg>` crosshair overlay (two lines + dot at `cx=55, cy=55`)
5. `<Svg>` tether line (rendered outside the clipped inner view, connects loupe edge to corner)

---

## Zoom Math

Extracted into `app-v2/utils/loupeMath.ts` as pure functions (testable without Reanimated).

### Image translation inside loupe

The image rendered inside the loupe has dimensions `frameW * 2.5 × frameH * 2.5`. To centre the active corner pixel at the loupe centre (55, 55):

```ts
export function calcImageTranslation(
  activeCX: number,
  activeCY: number,
  offsetX: number,
  offsetY: number,
  zoom: number,       // 2.5
  loupeRadius: number // 55
): { translateX: number; translateY: number } {
  return {
    translateX: loupeRadius - (activeCX - offsetX) * zoom,
    translateY: loupeRadius - (activeCY - offsetY) * zoom,
  }
}
```

### Loupe container position

```ts
export function calcLoupePosition(
  activeCX: number,
  activeCY: number,
  offsetY: number,
  loupeDiameter: number, // 110
  flipThreshold: number, // 120
  aboveOffset: number,   // 75
  belowOffset: number,   // 40
): { top: number; left: number } {
  const nearTop = (activeCY - offsetY) < flipThreshold
  return {
    top: nearTop
      ? activeCY + belowOffset
      : activeCY - aboveOffset - loupeDiameter,
    left: activeCX - loupeDiameter / 2,
  }
}
```

Both functions are called inside `useAnimatedStyle` worklets in `LoupeView`.

---

## Data Flow

```
CornerHandle.onStart
  → isDragging.value = 1       (UI thread, SharedValue)

CornerHandle.onUpdate
  → activeCX.value = cx.value  (UI thread, SharedValue)
  → activeCY.value = cy.value  (UI thread, SharedValue)

LoupeView.useAnimatedStyle (outer)
  → reads activeCX, activeCY, isDragging
  → computes loupe top/left + opacity
  → no JS bridge hop — pure UI thread

LoupeView.useAnimatedStyle (inner image)
  → reads activeCX, activeCY
  → computes Image translateX/Y
  → no JS bridge hop

CornerHandle.onEnd
  → isDragging.value = 0
  → runOnJS(onDragEnd)() → emitChange() → onQuadChange callback
```

The loupe position and image translation update at 60fps on the UI thread with zero JS involvement.

---

## Files Changed

| File | Change |
|------|--------|
| `app-v2/components/CropOverlay.tsx` | Add `imageUri` prop, `activeCX/Y/isDragging` shared values, extend `CornerHandle` with `onDragActive` worklet, add `LoupeView` sub-component |
| `app-v2/utils/loupeMath.ts` | New file — `calcImageTranslation`, `calcLoupePosition` pure functions |
| `app-v2/utils/__tests__/loupeMath.test.ts` | New file — unit tests for both math functions |
| `app-v2/app/(tabs)/crop-preview.tsx` | Pass `imageUri={currentImage.uri}` to `<CropOverlay>` |

---

## Testing

**Unit tests (`loupeMath.test.ts`):**
- `calcImageTranslation`: corner at centre of frame → image centred; corner at top-left → image at max positive offset; corner at bottom-right → image at max negative offset
- `calcLoupePosition`: corner above flip threshold → loupe below; corner below flip threshold → loupe above; corner at exact threshold boundary

**Manual verification checklist:**
- [ ] Loupe appears instantly on drag start, disappears on drag end
- [ ] Loupe crosshair aligns with the visible corner circle (confirms zoom math is correct)
- [ ] Dragging top-left corner (near top edge): loupe flips below
- [ ] Dragging bottom-right corner: loupe above, not clipped by screen edge
- [ ] All 4 corners independently trigger the loupe
- [ ] Hint text fades while dragging, returns after drag ends
- [ ] "Looks Good" flow still works correctly (loupe has no effect on quad state)

---

## Out of Scope

- Simultaneous multi-corner drag (not possible with standard single-touch pan)
- Loupe on initial auto-detected quad (only triggers on user drag)
- Haptic feedback on drag start/end
