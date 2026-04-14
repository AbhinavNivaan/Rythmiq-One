/**
 * loupeMath — pure geometry helpers for the crop-preview loupe overlay.
 *
 * Both functions are called from Reanimated useAnimatedStyle worklets.
 * They contain only arithmetic — no React Native imports.
 */

/**
 * Computes the Image translation needed to centre the active corner pixel
 * at the loupe centre (loupeRadius, loupeRadius).
 *
 * The image rendered inside the loupe has dimensions frameW*zoom × frameH*zoom.
 * offsetX/offsetY are the letterbox offsets (from getImageFrame in CropOverlay).
 */
export function calcImageTranslation(
  activeCX: number,
  activeCY: number,
  offsetX: number,
  offsetY: number,
  zoom: number,
  loupeRadius: number,
): { translateX: number; translateY: number } {
  return {
    translateX: loupeRadius - (activeCX - offsetX) * zoom,
    translateY: loupeRadius - (activeCY - offsetY) * zoom,
  }
}

/**
 * Computes the absolute top/left position of the loupe container.
 *
 * Default: 75pt above the corner, horizontally centred on it.
 * Flip: when corner is within flipThreshold pt of the image top,
 *       the loupe appears belowOffset pt below the corner instead.
 * left is clamped to [0, containerWidth - loupeDiameter].
 */
export function calcLoupePosition(
  activeCX: number,
  activeCY: number,
  offsetY: number,
  containerWidth: number,
  loupeDiameter: number,
  flipThreshold: number,
  aboveOffset: number,
  belowOffset: number,
): { top: number; left: number } {
  const nearTop = (activeCY - offsetY) < flipThreshold
  const top = nearTop
    ? activeCY + belowOffset
    : activeCY - aboveOffset - loupeDiameter
  const left = Math.max(
    0,
    Math.min(containerWidth - loupeDiameter, activeCX - loupeDiameter / 2),
  )
  return { top, left }
}
