import React from 'react';
import { StyleSheet, View, ViewStyle } from 'react-native';
import Colors from '../../constants/Colors';

export type CardVariant = 'default' | 'elevated' | 'glass';

interface CardProps {
  children: React.ReactNode;
  style?: ViewStyle;
  variant?: CardVariant;
}

export default function Card({ children, style, variant = 'default' }: CardProps) {
  const bg = {
    default:  Colors.semantic.surface,
    elevated: Colors.semantic.surfaceElevated,
    glass:    'rgba(25,27,38,0.70)',
  }[variant];

  return (
    <View style={[styles.container, { backgroundColor: bg }, style]}>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderRadius: 24,
    padding: 24,
    width: '100%',
    borderWidth: 1,
    borderColor: Colors.semantic.borderSubtle,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 5,
  },
});
