/**
 * CropOverlay
 *
 * Renders an interactive document crop quad overlay over an image.
 * - Draggable white corner circles (56pt hit target, 14pt visible radius)
 * - Blue quad outline + dim outside the quad
 * - Floating magnifier loupe (2.5×) while dragging a corner
 * - Quad coords are normalised 0.0–1.0 relative to the original image dimensions
 * - Accounts for resizeMode="contain" letterboxing inside the container
 */

import React, { useCallback } from 'react'
import { StyleSheet, View } from 'react-native'
import Svg, { Circle, Path, Line } from 'react-native-svg'
import { Gesture, GestureDetector } from 'react-native-gesture-handler'
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  useAnimatedProps,
  runOnJS,
} from 'react-native-reanimated'

import type { NormalisedQuad } from '../stores/captureSession'
import Colors from '../constants/Colors'
import { calcImageTranslation, calcLoupePosition } from '../utils/loupeMath'

const AnimatedCircle = Animated.createAnimatedComponent(Circle)
const AnimatedPath = Animated.createAnimatedComponent(Path)
const AnimatedLine = Animated.createAnimatedComponent(Line)

const CORNER_HIT_SIZE = 56
const CORNER_RADIUS = 14
const LOUPE_DIAMETER = 110
const LOUPE_RADIUS = 55
const ZOOM = 2.5
const FLIP_THRESHOLD = 120
const ABOVE_OFFSET = 75
const BELOW_OFFSET = 40

// Compute the image's rendered frame inside a contain-mode container
function getImageFrame(
  imageW: number,
  imageH: number,
  containerW: number,
  containerH: number,
) {
  const imageAspect = imageW / imageH
  const containerAspect = containerW / containerH
  let frameW: number, frameH: number
  if (imageAspect > containerAspect) {
    frameW = containerW
    frameH = containerW / imageAspect
  } else {
    frameH = containerH
    frameW = containerH * imageAspect
  }
  return {
    offsetX: (containerW - frameW) / 2,
    offsetY: (containerH - frameH) / 2,
    frameW,
    frameH,
  }
}

// --- LoupeView ---------------------------------------------------------------

interface LoupeViewProps {
  imageUri: string
  activeCX: Animated.SharedValue<number>
  activeCY: Animated.SharedValue<number>
  isDragging: Animated.SharedValue<number>
  containerWidth: number
  containerHeight: number
  offsetX: number
  offsetY: number
  frameW: number
  frameH: number
}

function LoupeView({
  imageUri,
  activeCX,
  activeCY,
  isDragging,
  containerWidth,
  containerHeight,
  offsetX,
  offsetY,
  frameW,
  frameH,
}: LoupeViewProps) {
  // Outer animated style — controls position and visibility
  const outerStyle = useAnimatedStyle(() => {
    const { top, left } = calcLoupePosition(
      activeCX.value,
      activeCY.value,
      offsetY,
      containerWidth,
      LOUPE_DIAMETER,
      FLIP_THRESHOLD,
      ABOVE_OFFSET,
      BELOW_OFFSET,
    )
    return {
      position: 'absolute',
      top,
      left,
      width: LOUPE_DIAMETER,
      height: LOUPE_DIAMETER,
      opacity: isDragging.value,
    }
  })

  // Image translation — centres the active corner pixel at the loupe centre
  const imageStyle = useAnimatedStyle(() => {
    const { translateX, translateY } = calcImageTranslation(
      activeCX.value,
      activeCY.value,
      offsetX,
      offsetY,
      ZOOM,
      LOUPE_RADIUS,
    )
    return {
      width: frameW * ZOOM,
      height: frameH * ZOOM,
      transform: [{ translateX }, { translateY }],
    }
  })

  // Tether animated props — dashed line from loupe edge to corner
  const tetherProps = useAnimatedProps(() => {
    const { top, left } = calcLoupePosition(
      activeCX.value,
      activeCY.value,
      offsetY,
      containerWidth,
      LOUPE_DIAMETER,
      FLIP_THRESHOLD,
      ABOVE_OFFSET,
      BELOW_OFFSET,
    )
    const nearTop = (activeCY.value - offsetY) < FLIP_THRESHOLD
    const loupeCenterX = left + LOUPE_RADIUS
    const loupeEdgeY = nearTop ? top : top + LOUPE_DIAMETER
    return {
      x1: loupeCenterX,
      y1: loupeEdgeY,
      x2: activeCX.value,
      y2: activeCY.value,
      opacity: isDragging.value * 0.45,
    }
  })

  return (
    <>
      {/* Circular loupe — clipped image + crosshair */}
      <Animated.View style={outerStyle} pointerEvents="none">
        <View
          style={{
            width: LOUPE_DIAMETER,
            height: LOUPE_DIAMETER,
            borderRadius: LOUPE_RADIUS,
            overflow: 'hidden',
          }}
        >
          <Animated.Image
            source={{ uri: imageUri }}
            style={imageStyle}
            resizeMode="cover"
          />
          {/* Crosshair — rendered on top of the image, inside the clip */}
          <Svg
            width={LOUPE_DIAMETER}
            height={LOUPE_DIAMETER}
            style={StyleSheet.absoluteFillObject}
          >
            {/* Horizontal arm */}
            <Line
              x1={LOUPE_RADIUS - 10}
              y1={LOUPE_RADIUS}
              x2={LOUPE_RADIUS + 10}
              y2={LOUPE_RADIUS}
              stroke={Colors.palette.blue400}
              strokeWidth={1.5}
              strokeOpacity={0.7}
            />
            {/* Vertical arm */}
            <Line
              x1={LOUPE_RADIUS}
              y1={LOUPE_RADIUS - 10}
              x2={LOUPE_RADIUS}
              y2={LOUPE_RADIUS + 10}
              stroke={Colors.palette.blue400}
              strokeWidth={1.5}
              strokeOpacity={0.7}
            />
            {/* Centre dot */}
            <Circle
              cx={LOUPE_RADIUS}
              cy={LOUPE_RADIUS}
              r={1.25}
              fill={Colors.palette.blue400}
              fillOpacity={0.7}
            />
          </Svg>
        </View>
      </Animated.View>

      {/* Tether — dashed line from loupe edge to corner, over full container */}
      <Svg
        width={containerWidth}
        height={containerHeight}
        style={[StyleSheet.absoluteFillObject, { pointerEvents: 'none' }]}
      >
        <AnimatedLine
          animatedProps={tetherProps}
          stroke={Colors.palette.blue400}
          strokeWidth={1.5}
          strokeDasharray="3,2.5"
        />
      </Svg>
    </>
  )
}

// --- CornerHandle ----------------------------------------------------------

interface CornerHandleProps {
  cx: Animated.SharedValue<number>
  cy: Animated.SharedValue<number>
  minX: number
  maxX: number
  minY: number
  maxY: number
  onDragEnd: () => void
  // Loupe wiring
  activeCX: Animated.SharedValue<number>
  activeCY: Animated.SharedValue<number>
  isDragging: Animated.SharedValue<number>
}

function CornerHandle({
  cx, cy, minX, maxX, minY, maxY, onDragEnd,
  activeCX, activeCY, isDragging,
}: CornerHandleProps) {
  const startX = useSharedValue(0)
  const startY = useSharedValue(0)

  const gesture = Gesture.Pan()
    .onStart(() => {
      startX.value = cx.value
      startY.value = cy.value
      // Set position BEFORE isDragging=1 to prevent a one-frame jump to (0,0)
      activeCX.value = cx.value
      activeCY.value = cy.value
      isDragging.value = 1
    })
    .onUpdate(e => {
      cx.value = Math.max(minX, Math.min(maxX, startX.value + e.translationX))
      cy.value = Math.max(minY, Math.min(maxY, startY.value + e.translationY))
      activeCX.value = cx.value
      activeCY.value = cy.value
    })
    .onEnd(() => {
      isDragging.value = 0
      runOnJS(onDragEnd)()
    })

  const animStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: cx.value - CORNER_HIT_SIZE / 2 },
      { translateY: cy.value - CORNER_HIT_SIZE / 2 },
    ],
  }))

  return (
    <GestureDetector gesture={gesture}>
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
}

// --- CropOverlay -----------------------------------------------------------

interface Props {
  containerWidth: number
  containerHeight: number
  /** Native pixel dimensions of the captured image (for contain-mode letterbox calc) */
  imageNativeWidth: number
  imageNativeHeight: number
  /** Initial quad in normalised 0.0–1.0 space relative to the original image */
  initialQuad: NormalisedQuad
  onQuadChange: (quad: NormalisedQuad) => void
  /** URI of the image being cropped — passed to LoupeView for the zoomed thumbnail */
  imageUri: string
}

export default function CropOverlay({
  containerWidth,
  containerHeight,
  imageNativeWidth,
  imageNativeHeight,
  initialQuad,
  onQuadChange,
  imageUri,
}: Props) {
  const { offsetX, offsetY, frameW, frameH } = getImageFrame(
    imageNativeWidth, imageNativeHeight, containerWidth, containerHeight,
  )

  // Convert normalised → display pixel (within the image frame)
  const toPixel = (nx: number, ny: number) => ({
    px: offsetX + nx * frameW,
    py: offsetY + ny * frameH,
  })

  const p0 = toPixel(initialQuad[0][0], initialQuad[0][1])
  const p1 = toPixel(initialQuad[1][0], initialQuad[1][1])
  const p2 = toPixel(initialQuad[2][0], initialQuad[2][1])
  const p3 = toPixel(initialQuad[3][0], initialQuad[3][1])

  const c0x = useSharedValue(p0.px); const c0y = useSharedValue(p0.py)
  const c1x = useSharedValue(p1.px); const c1y = useSharedValue(p1.py)
  const c2x = useSharedValue(p2.px); const c2y = useSharedValue(p2.py)
  const c3x = useSharedValue(p3.px); const c3y = useSharedValue(p3.py)

  const activeCX = useSharedValue(0)
  const activeCY = useSharedValue(0)
  const isDragging = useSharedValue(0)

  const emitChange = useCallback(() => {
    const toNorm = (px: number, py: number): [number, number] => [
      Math.max(0, Math.min(1, (px - offsetX) / frameW)),
      Math.max(0, Math.min(1, (py - offsetY) / frameH)),
    ]
    onQuadChange([
      toNorm(c0x.value, c0y.value),
      toNorm(c1x.value, c1y.value),
      toNorm(c2x.value, c2y.value),
      toNorm(c3x.value, c3y.value),
    ] as NormalisedQuad)
  }, [offsetX, offsetY, frameW, frameH, onQuadChange, c0x, c0y, c1x, c1y, c2x, c2y, c3x, c3y])

  // Dim area: outer rect minus the quad (evenodd rule)
  const dimProps = useAnimatedProps(() => {
    const outer = `M0,0 L${containerWidth},0 L${containerWidth},${containerHeight} L0,${containerHeight} Z`
    const inner = `M${c0x.value},${c0y.value} L${c1x.value},${c1y.value} L${c2x.value},${c2y.value} L${c3x.value},${c3y.value} Z`
    return { d: `${outer} ${inner}` }
  })

  // Quad stroke outline
  const strokeProps = useAnimatedProps(() => ({
    d: `M${c0x.value},${c0y.value} L${c1x.value},${c1y.value} L${c2x.value},${c2y.value} L${c3x.value},${c3y.value} Z`,
  }))

  const circ0Props = useAnimatedProps(() => ({ cx: c0x.value, cy: c0y.value }))
  const circ1Props = useAnimatedProps(() => ({ cx: c1x.value, cy: c1y.value }))
  const circ2Props = useAnimatedProps(() => ({ cx: c2x.value, cy: c2y.value }))
  const circ3Props = useAnimatedProps(() => ({ cx: c3x.value, cy: c3y.value }))

  const circleAnimProps = [circ0Props, circ1Props, circ2Props, circ3Props]

  const corners = [
    { cx: c0x, cy: c0y },
    { cx: c1x, cy: c1y },
    { cx: c2x, cy: c2y },
    { cx: c3x, cy: c3y },
  ]

  return (
    <View style={[StyleSheet.absoluteFillObject, { width: containerWidth, height: containerHeight }]}>
      <Svg width={containerWidth} height={containerHeight}>
        <AnimatedPath
          animatedProps={dimProps}
          fill="rgba(0,0,0,0.5)"
          fillRule="evenodd"
        />
        <AnimatedPath
          animatedProps={strokeProps}
          fill="none"
          stroke={Colors.palette.blue400}
          strokeWidth={2.5}
        />
        {circleAnimProps.map((props, i) => (
          <AnimatedCircle
            key={i}
            animatedProps={props}
            r={CORNER_RADIUS}
            fill={Colors.palette.neutral900}
            stroke={Colors.palette.blue400}
            strokeWidth={2.5}
          />
        ))}
      </Svg>

      {corners.map(({ cx, cy }, i) => (
        <CornerHandle
          key={i}
          cx={cx}
          cy={cy}
          minX={offsetX}
          maxX={offsetX + frameW}
          minY={offsetY}
          maxY={offsetY + frameH}
          onDragEnd={emitChange}
          activeCX={activeCX}
          activeCY={activeCY}
          isDragging={isDragging}
        />
      ))}

      <LoupeView
        imageUri={imageUri}
        activeCX={activeCX}
        activeCY={activeCY}
        isDragging={isDragging}
        containerWidth={containerWidth}
        containerHeight={containerHeight}
        offsetX={offsetX}
        offsetY={offsetY}
        frameW={frameW}
        frameH={frameH}
      />
    </View>
  )
}
