import React, { useState, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Dimensions,
  TouchableOpacity,
  Animated,
  FlatList,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import Svg, { Circle, Rect, Line, Path } from 'react-native-svg';

const { width, height } = Dimensions.get('window');
const CARD_W = width - 48;
const CARD_H = Math.min(height * 0.48, 400);
const CARD_BG = '#0E1020';
const MAYA_BLUE = '#89C7FE';
const INK_BLACK = '#070712';
const TRUE_COBALT = '#1A2595';
const WHITE = '#FCFEFF';
const DOC_FILL = '#131628';

// ─── Shared SVG primitives ───────────────────────────────────────────────────

/** Dot grid — must render inside <Svg> */
function DotGrid() {
  const spacing = 22;
  const dots: React.ReactNode[] = [];
  for (let x = spacing; x < CARD_W; x += spacing) {
    for (let y = spacing; y < CARD_H; y += spacing) {
      dots.push(
        <Circle key={`${x}:${y}`} cx={x} cy={y} r={1.2} fill={MAYA_BLUE} fillOpacity={0.1} />,
      );
    }
  }
  return <>{dots}</>;
}

/**
 * Blue glow around a rectangle — render BEFORE the rect itself.
 * cx/cy = centre of the rect, w/h = rect dimensions, rx = corner radius.
 */
function GlowRect({
  cx, cy, w, h, rx,
}: { cx: number; cy: number; w: number; h: number; rx: number }) {
  const layers = [
    { pad: 22, op: 0.03 },
    { pad: 12, op: 0.055 },
    { pad: 5,  op: 0.09 },
    { pad: 1,  op: 0.13 },
  ];
  return (
    <>
      {layers.map(({ pad, op }, i) => (
        <Rect
          key={i}
          x={cx - w / 2 - pad} y={cy - h / 2 - pad}
          width={w + pad * 2} height={h + pad * 2}
          rx={rx + pad * 0.5}
          fill={MAYA_BLUE} fillOpacity={op}
        />
      ))}
    </>
  );
}

/**
 * A document card with pill header + horizontal content lines.
 * cx/cy = centre, w/h = dimensions.
 */
function DocCard({
  cx, cy, w, h,
  rx = 10,
  strokeWidth = 1.5,
  strokeOpacity = 0.45,
  lineOpacity = 0.28,
  pillOpacity = 0.55,
  lineCount = 3,
}: {
  cx: number; cy: number; w: number; h: number;
  rx?: number; strokeWidth?: number; strokeOpacity?: number;
  lineOpacity?: number; pillOpacity?: number; lineCount?: number;
}) {
  const pillW = w * 0.46;
  const lineWidths = [0.78, 0.60, 0.72, 0.55].slice(0, lineCount);
  const bodyStart = cy - h / 2 + h * 0.32;
  const lineStep = (h * 0.52) / Math.max(lineCount - 1, 1);

  return (
    <>
      {/* Card */}
      <Rect
        x={cx - w / 2} y={cy - h / 2} width={w} height={h} rx={rx}
        fill={DOC_FILL} stroke={MAYA_BLUE} strokeWidth={strokeWidth} strokeOpacity={strokeOpacity}
      />
      {/* Pill header */}
      <Rect
        x={cx - pillW / 2} y={cy - h / 2 + 8} width={pillW} height={3.5} rx={1.75}
        fill={MAYA_BLUE} fillOpacity={pillOpacity}
      />
      {/* Content lines */}
      {lineWidths.map((lw, i) => (
        <Rect
          key={i}
          x={cx - w * lw / 2}
          y={bodyStart + i * lineStep}
          width={w * lw}
          height={2.5}
          rx={1.25}
          fill={MAYA_BLUE}
          fillOpacity={lineOpacity - i * 0.04}
        />
      ))}
    </>
  );
}

// ─── Slide 1: Camera viewfinder ───────────────────────────────────────────────

function UploadIllustration() {
  const vcx = CARD_W / 2;
  const vcy = CARD_H / 2;

  // Phone frame
  const fw = CARD_W * 0.55;
  const fh = CARD_H * 0.75;

  // Viewfinder (inner scanning area)
  const vw = fw * 0.68;
  const vh = fh * 0.55;
  const vx = vcx - vw / 2;
  const vy = vcy - vh / 2;

  // L-bracket arm length
  const lb = 20;
  const ls = 3;

  return (
    <Svg width={CARD_W} height={CARD_H}>
      <DotGrid />

      {/* Phone outer frame */}
      <Rect
        x={vcx - fw / 2} y={vcy - fh / 2} width={fw} height={fh} rx={20}
        fill={DOC_FILL} stroke={MAYA_BLUE} strokeOpacity={0.25} strokeWidth={1.5}
      />

      {/* Camera notch at top of phone */}
      <Rect
        x={vcx - fw * 0.18} y={vcy - fh / 2 + 10} width={fw * 0.36} height={5} rx={2.5}
        fill={MAYA_BLUE} fillOpacity={0.35}
      />

      {/* Home indicator at bottom of phone */}
      <Rect
        x={vcx - fw * 0.2} y={vcy + fh / 2 - 16} width={fw * 0.4} height={4} rx={2}
        fill={MAYA_BLUE} fillOpacity={0.25}
      />

      {/* Viewfinder area subtle fill */}
      <Rect
        x={vx} y={vy} width={vw} height={vh} rx={4}
        fill={MAYA_BLUE} fillOpacity={0.04}
        stroke={MAYA_BLUE} strokeOpacity={0.12} strokeWidth={1}
      />

      {/* TL bracket */}
      <Path
        d={`M ${vx + lb} ${vy} L ${vx} ${vy} L ${vx} ${vy + lb}`}
        fill="none" stroke={MAYA_BLUE} strokeWidth={ls}
        strokeLinecap="round" strokeLinejoin="round"
      />
      {/* TR bracket */}
      <Path
        d={`M ${vx + vw - lb} ${vy} L ${vx + vw} ${vy} L ${vx + vw} ${vy + lb}`}
        fill="none" stroke={MAYA_BLUE} strokeWidth={ls}
        strokeLinecap="round" strokeLinejoin="round"
      />
      {/* BR bracket */}
      <Path
        d={`M ${vx + vw} ${vy + vh - lb} L ${vx + vw} ${vy + vh} L ${vx + vw - lb} ${vy + vh}`}
        fill="none" stroke={MAYA_BLUE} strokeWidth={ls}
        strokeLinecap="round" strokeLinejoin="round"
      />
      {/* BL bracket */}
      <Path
        d={`M ${vx} ${vy + vh - lb} L ${vx} ${vy + vh} L ${vx + lb} ${vy + vh}`}
        fill="none" stroke={MAYA_BLUE} strokeWidth={ls}
        strokeLinecap="round" strokeLinejoin="round"
      />

      {/* Scan line with extended glow strips */}
      <Rect
        x={vx + 6} y={vcy - 2} width={vw - 12} height={4} rx={2}
        fill={MAYA_BLUE} fillOpacity={0.08}
      />
      <Line
        x1={vx + 6} y1={vcy} x2={vx + vw - 6} y2={vcy}
        stroke={MAYA_BLUE} strokeWidth={1.8} strokeOpacity={0.75}
      />
    </Svg>
  );
}

// ─── Slide 2: Concentric rings + master document ──────────────────────────────

function MasterIllustration() {
  const vcx = CARD_W / 2;
  const vcy = CARD_H / 2;

  const r1 = CARD_W * 0.17;
  const r2 = CARD_W * 0.28;
  const r3 = CARD_W * 0.40;

  const dw = CARD_W * 0.27;
  const dh = dw * 1.38;

  const ticks = (r: number, count: number, majorEvery: number) =>
    Array.from({ length: count }, (_, i) => {
      const a = (i / count) * 2 * Math.PI - Math.PI / 2;
      const major = i % majorEvery === 0;
      const len = major ? 10 : 5;
      return (
        <Line
          key={i}
          x1={vcx + Math.cos(a) * r}
          y1={vcy + Math.sin(a) * r}
          x2={vcx + Math.cos(a) * (r + len)}
          y2={vcy + Math.sin(a) * (r + len)}
          stroke={MAYA_BLUE}
          strokeWidth={major ? 1.5 : 0.8}
          strokeOpacity={major ? 0.6 : 0.25}
        />
      );
    });

  return (
    <Svg width={CARD_W} height={CARD_H}>
      <DotGrid />

      {/* Rings — outer to inner */}
      <Circle cx={vcx} cy={vcy} r={r3} fill="none" stroke={MAYA_BLUE} strokeWidth={0.8} strokeOpacity={0.18} />
      {ticks(r3, 24, 6)}

      <Circle cx={vcx} cy={vcy} r={r2} fill="none" stroke={MAYA_BLUE} strokeWidth={0.8} strokeOpacity={0.25} />
      {ticks(r2, 16, 4)}

      <Circle cx={vcx} cy={vcy} r={r1} fill="none" stroke={MAYA_BLUE} strokeWidth={1} strokeOpacity={0.35} />

      {/* Document glow */}
      <GlowRect cx={vcx} cy={vcy} w={dw} h={dh} rx={10} />

      {/* Document card */}
      <DocCard
        cx={vcx} cy={vcy} w={dw} h={dh}
        rx={10} strokeWidth={2} strokeOpacity={0.75}
        pillOpacity={0.7} lineOpacity={0.38} lineCount={4}
      />
    </Svg>
  );
}

// ─── Slide 3: Export radial diagram ──────────────────────────────────────────

function ExportIllustration() {
  const vcx = CARD_W / 2;
  const vcy = CARD_H / 2;

  // Master doc (centre)
  const mdw = CARD_W * 0.28;
  const mdh = mdw * 1.38;

  // Portal docs — angle (deg), distance (% CARD_W), width (% mdw), aspect ratio h/w
  const portals: Array<{ a: number; d: number; ws: number; ar: number }> = [
    { a: -90, d: 0.36, ws: 0.60, ar: 1.40 }, // top
    { a: -22, d: 0.40, ws: 0.52, ar: 1.15 }, // upper-right
    { a:  38, d: 0.40, ws: 0.56, ar: 1.35 }, // right
    { a: 128, d: 0.37, ws: 0.48, ar: 1.20 }, // lower-left
    { a: 175, d: 0.38, ws: 0.55, ar: 1.30 }, // left
  ];

  return (
    <Svg width={CARD_W} height={CARD_H}>
      <DotGrid />

      {/* Dashed beams + portal docs */}
      {portals.map((p, i) => {
        const rad = (p.a * Math.PI) / 180;
        const dist = CARD_W * p.d;
        const px = vcx + Math.cos(rad) * dist;
        const py = vcy + Math.sin(rad) * dist;
        const pw = mdw * p.ws;
        const ph = pw * p.ar;

        // Beam ends at edge of portal doc (approx), starts at edge of master
        const masterEdgeX = vcx + Math.cos(rad) * (mdw / 2 + 4);
        const masterEdgeY = vcy + Math.sin(rad) * (mdh / 2 + 4);
        const portalEdgeX = px - Math.cos(rad) * (pw / 2 + 4);
        const portalEdgeY = py - Math.sin(rad) * (ph / 2 + 4);

        return (
          <React.Fragment key={i}>
            {/* Dashed beam */}
            <Line
              x1={masterEdgeX} y1={masterEdgeY}
              x2={portalEdgeX} y2={portalEdgeY}
              stroke={MAYA_BLUE} strokeWidth={1.2} strokeOpacity={0.4}
              strokeDasharray="4,6"
            />
            {/* Portal doc */}
            <DocCard
              cx={px} cy={py} w={pw} h={ph}
              rx={9} strokeWidth={1.5} strokeOpacity={0.45}
              pillOpacity={0.5} lineOpacity={0.25} lineCount={3}
            />
          </React.Fragment>
        );
      })}

      {/* Master doc glow */}
      <GlowRect cx={vcx} cy={vcy} w={mdw} h={mdh} rx={12} />

      {/* Master doc (rendered last — on top of beams) */}
      <DocCard
        cx={vcx} cy={vcy} w={mdw} h={mdh}
        rx={12} strokeWidth={2.5} strokeOpacity={0.9}
        pillOpacity={0.75} lineOpacity={0.42} lineCount={4}
      />
    </Svg>
  );
}

// ─── Slide data ───────────────────────────────────────────────────────────────

interface Slide {
  id: string;
  title: string;
  description: string;
  Illustration: React.ComponentType;
}

const slides: Slide[] = [
  {
    id: 'upload',
    title: 'Upload Once',
    description: 'Point your camera at any document. We detect, crop, and enhance it automatically.',
    Illustration: UploadIllustration,
  },
  {
    id: 'master',
    title: 'Your Document. Perfected.',
    description: 'Encrypted, lossless, and stored for the long term — the best version, locked in forever.',
    Illustration: MasterIllustration,
  },
  {
    id: 'export',
    title: 'Export for Any Portal',
    description: "One master — instantly adapted to NEET, JEE, CAT, and any portal's exact specs.",
    Illustration: ExportIllustration,
  },
];

// ─── Screen ───────────────────────────────────────────────────────────────────

export default function OnboardingScreen() {
  const router = useRouter();
  const [currentIndex, setCurrentIndex] = useState(0);
  const flatListRef = useRef<any>(null);
  const scrollX = useRef(new Animated.Value(0)).current;

  const handleButton = () => {
    if (currentIndex < slides.length - 1) {
      flatListRef.current?.scrollToIndex({ index: currentIndex + 1, animated: true });
    } else {
      router.replace('/(auth)/login');
    }
  };

  const renderSlide = ({ item }: { item: Slide }) => (
    <View style={styles.slide}>
      <View style={styles.card}>
        <item.Illustration />
      </View>
      <Text style={styles.title}>{item.title}</Text>
      <Text style={styles.description}>{item.description}</Text>
    </View>
  );

  const renderDots = () => (
    <View style={styles.dotsRow}>
      {slides.map((_, i) => {
        const inputRange = [(i - 1) * width, i * width, (i + 1) * width];
        const dotWidth = scrollX.interpolate({
          inputRange,
          outputRange: [5, 18, 5],
          extrapolate: 'clamp',
        });
        const opacity = scrollX.interpolate({
          inputRange,
          outputRange: [0.3, 1, 0.3],
          extrapolate: 'clamp',
        });
        return (
          <Animated.View key={i} style={[styles.dot, { width: dotWidth, opacity }]} />
        );
      })}
    </View>
  );

  return (
    <SafeAreaView style={styles.container}>
      <Animated.FlatList
        ref={flatListRef}
        data={slides}
        renderItem={renderSlide}
        keyExtractor={(item) => item.id}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        bounces={false}
        onScroll={Animated.event(
          [{ nativeEvent: { contentOffset: { x: scrollX } } }],
          { useNativeDriver: false },
        )}
        onMomentumScrollEnd={(e) => {
          setCurrentIndex(Math.round(e.nativeEvent.contentOffset.x / width));
        }}
        scrollEventThrottle={16}
        style={styles.flatList}
      />

      {renderDots()}

      <View style={styles.buttonContainer}>
        <TouchableOpacity style={styles.button} onPress={handleButton} activeOpacity={0.8}>
          <Text style={styles.buttonText}>
            {currentIndex === slides.length - 1 ? 'Get Started' : 'Next'}
          </Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: INK_BLACK,
  },
  flatList: {
    flex: 1,
  },
  slide: {
    width,
    flex: 1,
    paddingHorizontal: 24,
    paddingTop: 16,
  },
  card: {
    width: CARD_W,
    height: CARD_H,
    borderRadius: 20,
    backgroundColor: CARD_BG,
    overflow: 'hidden',
    marginBottom: 24,
  },
  title: {
    fontSize: 26,
    fontWeight: '700',
    color: WHITE,
    marginBottom: 10,
    letterSpacing: -0.5,
  },
  description: {
    fontSize: 15,
    color: WHITE + 'AA',
    lineHeight: 22,
  },
  dotsRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
    gap: 6,
  },
  dot: {
    height: 5,
    borderRadius: 2.5,
    backgroundColor: MAYA_BLUE,
  },
  buttonContainer: {
    paddingHorizontal: 24,
    paddingBottom: 16,
  },
  button: {
    backgroundColor: TRUE_COBALT,
    paddingVertical: 16,
    borderRadius: 12,
    alignItems: 'center',
  },
  buttonText: {
    color: WHITE,
    fontSize: 17,
    fontWeight: '600',
  },
});
