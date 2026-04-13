/**
 * Skeleton Loader Components
 *
 * Provides loading placeholder animations for better perceived performance.
 */

import React, { useEffect, useRef } from 'react';
import { View, StyleSheet, Animated, ViewStyle } from 'react-native';
import Colors from '../../constants/Colors';

interface SkeletonProps {
  width?: number | string;
  height?: number | string;
  borderRadius?: number;
  style?: ViewStyle;
}

/**
 * Animated skeleton placeholder with shimmer effect using semantic surface tokens
 */
export function Skeleton({
  width = '100%',
  height = 16,
  borderRadius = 8,
  style,
}: SkeletonProps) {
  const animatedValue = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(animatedValue, {
          toValue: 1,
          duration: 1000,
          useNativeDriver: false,
        }),
        Animated.timing(animatedValue, {
          toValue: 0,
          duration: 1000,
          useNativeDriver: false,
        }),
      ])
    );
    animation.start();

    return () => animation.stop();
  }, [animatedValue]);

  const backgroundColor = animatedValue.interpolate({
    inputRange: [0, 1],
    outputRange: [Colors.semantic.surface, Colors.semantic.surfaceElevated],
  });

  return (
    <Animated.View
      style={[
        {
          width: width as any,
          height: height as any,
          borderRadius,
          backgroundColor,
        },
        style,
      ]}
    />
  );
}

/**
 * Document card skeleton
 */
export function DocumentCardSkeleton() {
  return (
    <View style={styles.card}>
      {/* Thumbnail */}
      <Skeleton width={80} height={80} borderRadius={12} />
      
      {/* Content */}
      <View style={styles.cardContent}>
        <Skeleton width="60%" height={16} style={{ marginBottom: 8 }} />
        <Skeleton width="40%" height={12} style={{ marginBottom: 12 }} />
        <View style={styles.cardMeta}>
          <Skeleton width={60} height={20} borderRadius={10} />
          <Skeleton width={80} height={12} />
        </View>
      </View>
    </View>
  );
}

/**
 * List of document card skeletons
 */
export function DocumentListSkeleton({ count = 5 }: { count?: number }) {
  return (
    <View style={styles.list}>
      {Array.from({ length: count }).map((_, index) => (
        <DocumentCardSkeleton key={index} />
      ))}
    </View>
  );
}

/**
 * Job detail screen skeleton
 */
export function JobDetailSkeleton() {
  return (
    <View style={styles.detailContainer}>
      {/* Status card */}
      <View style={styles.statusCard}>
        <Skeleton width={80} height={80} borderRadius={40} style={{ marginBottom: 16 }} />
        <Skeleton width={120} height={24} style={{ marginBottom: 8 }} />
        <Skeleton width={180} height={14} />
      </View>

      {/* Info section */}
      <View style={styles.infoSection}>
        <Skeleton width={80} height={12} style={{ marginBottom: 16 }} />
        <View style={styles.infoRow}>
          <Skeleton width={60} height={16} />
          <Skeleton width={100} height={14} />
        </View>
        <View style={styles.infoRow}>
          <Skeleton width={80} height={16} />
          <Skeleton width={60} height={24} borderRadius={12} />
        </View>
      </View>

      {/* Action buttons */}
      <View style={styles.actionSection}>
        <Skeleton width="100%" height={52} borderRadius={12} style={{ marginBottom: 12 }} />
        <Skeleton width="100%" height={48} borderRadius={12} />
      </View>
    </View>
  );
}

/**
 * Portal list skeleton
 */
export function PortalListSkeleton({ count = 6 }: { count?: number }) {
  return (
    <View style={styles.portalList}>
      {Array.from({ length: count }).map((_, index) => (
        <View key={index} style={styles.portalItem}>
          <Skeleton width={48} height={48} borderRadius={12} />
          <View style={{ flex: 1, marginLeft: 12 }}>
            <Skeleton width="70%" height={16} style={{ marginBottom: 6 }} />
            <Skeleton width="50%" height={12} />
          </View>
        </View>
      ))}
    </View>
  );
}

/**
 * Dashboard stats skeleton
 */
export function DashboardStatsSkeleton() {
  return (
    <View style={styles.statsContainer}>
      <View style={styles.statCard}>
        <Skeleton width={40} height={40} borderRadius={12} style={{ marginBottom: 12 }} />
        <Skeleton width={48} height={28} style={{ marginBottom: 8 }} />
        <Skeleton width={80} height={12} />
      </View>
      <View style={styles.statCard}>
        <Skeleton width={40} height={40} borderRadius={12} style={{ marginBottom: 12 }} />
        <Skeleton width={48} height={28} style={{ marginBottom: 8 }} />
        <Skeleton width={80} height={12} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    backgroundColor: Colors.semantic.surface,
    borderRadius: 16,
    padding: 16,
    marginBottom: 12,
  },
  cardContent: {
    flex: 1,
    marginLeft: 16,
    justifyContent: 'center',
  },
  cardMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  list: {
    paddingHorizontal: 16,
  },
  detailContainer: {
    padding: 16,
  },
  statusCard: {
    backgroundColor: Colors.semantic.surface,
    borderRadius: 20,
    padding: 32,
    alignItems: 'center',
    marginBottom: 24,
  },
  infoSection: {
    backgroundColor: Colors.semantic.surface,
    borderRadius: 16,
    padding: 16,
    marginBottom: 16,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: Colors.semantic.borderSubtle,
  },
  actionSection: {
    backgroundColor: Colors.semantic.surface,
    borderRadius: 16,
    padding: 16,
    marginBottom: 16,
  },
  portalList: {
    padding: 16,
  },
  portalItem: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.semantic.surface,
    borderRadius: 16,
    padding: 16,
    marginBottom: 12,
  },
  statsContainer: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    gap: 12,
  },
  statCard: {
    flex: 1,
    backgroundColor: Colors.semantic.surface,
    borderRadius: 16,
    padding: 16,
    alignItems: 'center',
  },
});

export default {
  Skeleton,
  DocumentCardSkeleton,
  DocumentListSkeleton,
  JobDetailSkeleton,
  PortalListSkeleton,
  DashboardStatsSkeleton,
};
