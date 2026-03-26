/**
 * CropOverlay
 *
 * Renders an interactive document crop quad overlay over an image.
 * - Draggable white corner circles (40pt hit target, 12pt visible radius)
 * - Blue quad lines
 * - Blue edge midpoint handles (decorative, not draggable)
 * - Dimmed outside-quad area using SVG fill-rule evenodd
 * - Calls onQuadChange with normalised coords after each drag
 */

import React, { useCallback } from 'react'
import { StyleSheet, View } from 'react-native'
import Svg, { Polygon, Circle, Rect, Path } from 'react-native-svg'
import { Gesture, GestureDetector } from 'react-native-gesture-handler'
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  runOnJS,
} from 'react-native-reanimated'

import type { NormalisedQuad } from '../stores/captureSession'

interface Props {
  /** Display dimensions of the image container */
  containerWidth: number
  containerHeight: number
  /** Initial quad in normalised 0.0–1.0 space */
  initialQuad: NormalisedQuad
  /** Called when the user finishes dragging a corner, with updated normalised quad */
  onQuadChange: (quad: NormalisedQuad) => void
}

const CORNER_HIT_SIZE = 40   // transparent hit target
const CORNER_RADIUS = 12     // visible circle radius
const MIDPOINT_SIZE = 10     // edge midpoint indicator

export default function CropOverlay({
  containerWidth,
  containerHeight,
  initialQuad,
  onQuadChange,
}: Props) {
  // Each corner: shared values in DISPLAY pixel space
  const corners = [0, 1, 2, 3].map(i => ({
    x: useSharedValue(initialQuad[i][0] * containerWidth),
    y: useSharedValue(initialQuad[i][1] * containerHeight),
  }))

  const emitChange = useCallback(() => {
    const quad: NormalisedQuad = corners.map(c => [
      Math.max(0, Math.min(1, c.x.value / containerWidth)),
      Math.max(0, Math.min(1, c.y.value / containerHeight)),
    ]) as NormalisedQuad
    onQuadChange(quad)
  }, [containerWidth, containerHeight, onQuadChange])

  const makeCornerGesture = (index: number) =>
    Gesture.Pan()
      .onUpdate(e => {
        corners[index].x.value = Math.max(0, Math.min(containerWidth, e.absoluteX))
        corners[index].y.value = Math.max(0, Math.min(containerHeight, e.absoluteY))
      })
      .onEnd(() => {
        runOnJS(emitChange)()
      })

  // Build polygon points string for SVG from shared values
  const polygonPoints = corners
    .map(c => `${c.x.value},${c.y.value}`)
    .join(' ')

  // Midpoints of each edge
  const midpoints = [
    { x: (corners[0].x.value + corners[1].x.value) / 2, y: (corners[0].y.value + corners[1].y.value) / 2 },
    { x: (corners[1].x.value + corners[2].x.value) / 2, y: (corners[1].y.value + corners[2].y.value) / 2 },
    { x: (corners[2].x.value + corners[3].x.value) / 2, y: (corners[2].y.value + corners[3].y.value) / 2 },
    { x: (corners[3].x.value + corners[0].x.value) / 2, y: (corners[3].y.value + corners[0].y.value) / 2 },
  ]

  const dimPath = `M0,0 L${containerWidth},0 L${containerWidth},${containerHeight} L0,${containerHeight} Z ` +
    `M${polygonPoints} Z`

  return (
    <View style={[StyleSheet.absoluteFillObject, { width: containerWidth, height: containerHeight }]}>
      <Svg width={containerWidth} height={containerHeight}>
        {/* Dimmed outside area */}
        <Path
          d={dimPath}
          fill="rgba(0,0,0,0.5)"
          fillRule="evenodd"
        />
        {/* Quad outline */}
        <Polygon
          points={polygonPoints}
          fill="none"
          stroke="#89C7FE"
          strokeWidth={2.5}
        />
        {/* Edge midpoint indicators */}
        {midpoints.map((mp, i) => (
          <Rect
            key={`mid-${i}`}
            x={mp.x - MIDPOINT_SIZE / 2}
            y={mp.y - MIDPOINT_SIZE / 2}
            width={MIDPOINT_SIZE}
            height={MIDPOINT_SIZE}
            rx={4}
            fill="#89C7FE"
          />
        ))}
        {/* Corner circles (visual only — gesture targets are Views below) */}
        {corners.map((c, i) => (
          <Circle
            key={`circle-${i}`}
            cx={c.x.value}
            cy={c.y.value}
            r={CORNER_RADIUS}
            fill="#FCFEFF"
            stroke="#89C7FE"
            strokeWidth={2.5}
          />
        ))}
      </Svg>

      {/* Draggable hit targets — transparent Views positioned over each corner */}
      {corners.map((c, i) => {
        const animStyle = useAnimatedStyle(() => ({
          transform: [
            { translateX: c.x.value - CORNER_HIT_SIZE / 2 },
            { translateY: c.y.value - CORNER_HIT_SIZE / 2 },
          ],
        }))
        return (
          <GestureDetector key={`gesture-${i}`} gesture={makeCornerGesture(i)}>
            <Animated.View
              style={[
                {
                  position: 'absolute',
                  width: CORNER_HIT_SIZE,
                  height: CORNER_HIT_SIZE,
                  top: 0,
                  left: 0,
                },
                animStyle,
              ]}
            />
          </GestureDetector>
        )
      })}
    </View>
  )
}
