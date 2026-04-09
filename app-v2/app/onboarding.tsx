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

// Shared dot-grid overlay — renders inside an <Svg>
function DotGrid() {
  const spacing = 22;
  const dots: React.ReactNode[] = [];
  for (let x = spacing; x < CARD_W; x += spacing) {
    for (let y = spacing; y < CARD_H; y += spacing) {
      dots.push(
        <Circle key={`${x}${y}`} cx={x} cy={y} r={1} fill={MAYA_BLUE} fillOpacity={0.07} />
      );
    }
  }
  return <>{dots}</>;
}

// Slide 1: camera viewfinder with L-bracket corner markers + scan line
function UploadIllustration() {
  const vcx = CARD_W / 2;
  const vcy = CARD_H / 2;
  const fw = CARD_W * 0.52;
  const fh = CARD_H * 0.68;
  const vw = fw * 0.72;
  const vh = fh * 0.58;
  const vx = vcx - vw / 2;
  const vy = vcy - vh / 2;
  const lb = 18;
  const ls = 2.5;

  return (
    <Svg width={CARD_W} height={CARD_H}>
      <DotGrid />
      {/* Phone outline */}
      <Rect
        x={vcx - fw / 2} y={vcy - fh / 2}
        width={fw} height={fh} rx={16}
        fill="none" stroke={MAYA_BLUE} strokeOpacity={0.18} strokeWidth={1.5}
      />
      {/* Viewfinder fill */}
      <Rect
        x={vx} y={vy} width={vw} height={vh} rx={3}
        fill={MAYA_BLUE} fillOpacity={0.04}
        stroke={MAYA_BLUE} strokeOpacity={0.1} strokeWidth={1}
      />
      {/* TL bracket */}
      <Path d={`M ${vx+lb} ${vy} L ${vx} ${vy} L ${vx} ${vy+lb}`}
        fill="none" stroke={MAYA_BLUE} strokeWidth={ls} strokeLinecap="round" strokeLinejoin="round" />
      {/* TR bracket */}
      <Path d={`M ${vx+vw-lb} ${vy} L ${vx+vw} ${vy} L ${vx+vw} ${vy+lb}`}
        fill="none" stroke={MAYA_BLUE} strokeWidth={ls} strokeLinecap="round" strokeLinejoin="round" />
      {/* BR bracket */}
      <Path d={`M ${vx+vw} ${vy+vh-lb} L ${vx+vw} ${vy+vh} L ${vx+vw-lb} ${vy+vh}`}
        fill="none" stroke={MAYA_BLUE} strokeWidth={ls} strokeLinecap="round" strokeLinejoin="round" />
      {/* BL bracket */}
      <Path d={`M ${vx} ${vy+vh-lb} L ${vx} ${vy+vh} L ${vx+lb} ${vy+vh}`}
        fill="none" stroke={MAYA_BLUE} strokeWidth={ls} strokeLinecap="round" strokeLinejoin="round" />
      {/* Horizontal scan line */}
      <Line
        x1={vx + 6} y1={vcy} x2={vx + vw - 6} y2={vcy}
        stroke={MAYA_BLUE} strokeWidth={1.5} strokeOpacity={0.65}
      />
    </Svg>
  );
}

// Slide 2: document centred in 3 concentric rings with tick marks + cipher lines
function MasterIllustration() {
  const vcx = CARD_W / 2;
  const vcy = CARD_H / 2;
  const r1 = CARD_W * 0.18;
  const r2 = CARD_W * 0.28;
  const r3 = CARD_W * 0.39;
  const dw = CARD_W * 0.24;
  const dh = dw * 1.38;

  const ticks = (r: number, count: number, majorEvery: number) =>
    Array.from({ length: count }, (_, i) => {
      const a = (i / count) * 2 * Math.PI - Math.PI / 2;
      const major = i % majorEvery === 0;
      const len = major ? 8 : 5;
      return (
        <Line
          key={i}
          x1={vcx + Math.cos(a) * r}
          y1={vcy + Math.sin(a) * r}
          x2={vcx + Math.cos(a) * (r + len)}
          y2={vcy + Math.sin(a) * (r + len)}
          stroke={MAYA_BLUE}
          strokeWidth={major ? 1.5 : 0.8}
          strokeOpacity={major ? 0.55 : 0.22}
        />
      );
    });

  const cipherLines = [0.2, 0.32, 0.44, 0.56, 0.68, 0.8];
  const cipherWidths = [0.72, 0.9, 0.58, 0.85, 0.7, 0.5];

  return (
    <Svg width={CARD_W} height={CARD_H}>
      <DotGrid />
      <Circle cx={vcx} cy={vcy} r={r3} fill="none" stroke={MAYA_BLUE} strokeWidth={0.8} strokeOpacity={0.14} />
      {ticks(r3, 24, 6)}
      <Circle cx={vcx} cy={vcy} r={r2} fill="none" stroke={MAYA_BLUE} strokeWidth={0.8} strokeOpacity={0.2} />
      {ticks(r2, 16, 4)}
      <Circle cx={vcx} cy={vcy} r={r1} fill="none" stroke={MAYA_BLUE} strokeWidth={1} strokeOpacity={0.3} />
      <Rect
        x={vcx - dw / 2} y={vcy - dh / 2}
        width={dw} height={dh} rx={4}
        fill="#131628" stroke={MAYA_BLUE} strokeWidth={1.5} strokeOpacity={0.55}
      />
      {cipherLines.map((frac, i) => (
        <Rect
          key={i}
          x={vcx - dw / 2 + dw * 0.1}
          y={vcy - dh / 2 + dh * frac}
          width={dw * cipherWidths[i] * 0.8}
          height={2.5}
          rx={1.25}
          fill={MAYA_BLUE}
          fillOpacity={0.38}
        />
      ))}
    </Svg>
  );
}

// Slide 3: master doc in centre, 5 portal docs radiating via dashed beams
function ExportIllustration() {
  const vcx = CARD_W / 2;
  const vcy = CARD_H / 2;
  const mdw = CARD_W * 0.22;
  const mdh = mdw * 1.38;

  const portals: Array<{ a: number; d: number; ws: number; hs: number }> = [
    { a: -80, d: CARD_W * 0.34, ws: 0.55, hs: 0.68 },
    { a: -18, d: CARD_W * 0.38, ws: 0.48, hs: 0.62 },
    { a:  42, d: CARD_W * 0.36, ws: 0.60, hs: 0.72 },
    { a: 112, d: CARD_W * 0.35, ws: 0.44, hs: 0.58 },
    { a: 168, d: CARD_W * 0.38, ws: 0.56, hs: 0.70 },
  ];

  return (
    <Svg width={CARD_W} height={CARD_H}>
      <DotGrid />
      {portals.map((p, i) => {
        const rad = (p.a * Math.PI) / 180;
        const px = vcx + Math.cos(rad) * p.d;
        const py = vcy + Math.sin(rad) * p.d;
        const pw = mdw * p.ws;
        const ph = mdh * p.hs;
        return (
          <React.Fragment key={i}>
            <Line
              x1={vcx} y1={vcy} x2={px} y2={py}
              stroke={MAYA_BLUE} strokeWidth={1} strokeOpacity={0.3}
              strokeDasharray="4,7"
            />
            <Rect
              x={px - pw / 2} y={py - ph / 2}
              width={pw} height={ph} rx={3}
              fill="#131628" stroke={MAYA_BLUE} strokeWidth={1.2} strokeOpacity={0.38}
            />
          </React.Fragment>
        );
      })}
      <Rect
        x={vcx - mdw / 2} y={vcy - mdh / 2}
        width={mdw} height={mdh} rx={4}
        fill="#131628" stroke={MAYA_BLUE} strokeWidth={2} strokeOpacity={0.85}
      />
      {[0.25, 0.42, 0.58, 0.75].map((frac, i) => {
        const widths = [0.72, 0.88, 0.6, 0.78];
        return (
          <Rect
            key={i}
            x={vcx - mdw / 2 + mdw * 0.12}
            y={vcy - mdh / 2 + mdh * frac}
            width={mdw * widths[i] * 0.76}
            height={2.5}
            rx={1.25}
            fill={MAYA_BLUE}
            fillOpacity={0.5}
          />
        );
      })}
    </Svg>
  );
}

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
          <Animated.View
            key={i}
            style={[styles.dot, { width: dotWidth, opacity }]}
          />
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
          { useNativeDriver: false }
        )}
        onMomentumScrollEnd={(e) => {
          setCurrentIndex(Math.round(e.nativeEvent.contentOffset.x / width));
        }}
        scrollEventThrottle={16}
        style={styles.flatList}
      />
      {renderDots()}
      <View style={styles.buttonContainer}>
        <TouchableOpacity
          style={styles.button}
          onPress={handleButton}
          activeOpacity={0.8}
        >
          <Text style={styles.buttonText}>
            {currentIndex === slides.length - 1 ? 'Get Started' : 'Next'}
          </Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

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
    marginBottom: 28,
  },
  title: {
    fontSize: 26,
    fontWeight: '700',
    color: WHITE,
    marginBottom: 12,
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
    marginBottom: 20,
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
