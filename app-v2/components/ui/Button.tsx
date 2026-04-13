import React from 'react';
import { StyleSheet, Text, TouchableOpacity, ActivityIndicator, ViewStyle } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withSpring } from 'react-native-reanimated';
import Colors from '../../constants/Colors';
import Typography from '../../constants/Typography';

export type ButtonVariant =
  | 'primary-white'
  | 'primary-green'
  | 'secondary'
  | 'soft-danger'
  | 'ghost'
  | 'ghost-outline'
  | 'danger'
  | 'icon-round';

interface ButtonStyles {
  container: ViewStyle;
  textColor: string;
}

export function getButtonStyles(variant: ButtonVariant, disabled: boolean): ButtonStyles {
  if (disabled && variant !== 'icon-round') {
    return {
      container: { backgroundColor: Colors.disabled.fill, pointerEvents: 'none' as const },
      textColor: Colors.disabled.text,
    };
  }

  switch (variant) {
    case 'primary-white':
      return {
        container: { backgroundColor: Colors.palette.neutral900 },
        textColor: Colors.palette.neutral0,
      };
    case 'primary-green':
      return {
        container: { backgroundColor: Colors.palette.green },
        textColor: Colors.palette.neutral0,
      };
    case 'secondary':
      return {
        container: { backgroundColor: 'rgba(74,222,128,0.12)' },
        textColor: Colors.palette.green,
      };
    case 'soft-danger':
      return {
        container: { backgroundColor: 'rgba(239,68,68,0.12)' },
        textColor: Colors.palette.red,
      };
    case 'ghost':
      return {
        container: { backgroundColor: 'transparent' },
        textColor: `rgba(252,254,255,0.80)`,
      };
    case 'ghost-outline':
      return {
        container: {
          backgroundColor: 'transparent',
          borderWidth: 1.5,
          borderColor: 'rgba(252,254,255,0.20)',
        },
        textColor: `rgba(252,254,255,0.80)`,
      };
    case 'danger':
      return {
        container: {
          backgroundColor: 'transparent',
          borderWidth: 1.5,
          borderColor: Colors.palette.red,
        },
        textColor: Colors.palette.red,
      };
    case 'icon-round':
      return {
        container: {
          backgroundColor: Colors.semantic.surface,
          borderWidth: 1,
          borderColor: Colors.semantic.borderSubtle,
          width: 46,
          height: 46,
          borderRadius: 23,
        },
        textColor: Colors.palette.neutral900,
      };
  }
}

const AnimatedTouchable = Animated.createAnimatedComponent(TouchableOpacity);

interface ButtonProps {
  onPress: () => void;
  title?: string;
  variant?: ButtonVariant;
  isLoading?: boolean;
  style?: ViewStyle;
  disabled?: boolean;
  icon?: React.ReactNode;
}

export default function Button({
  onPress,
  title,
  variant = 'primary-white',
  isLoading = false,
  style,
  disabled = false,
  icon,
}: ButtonProps) {
  const scale = useSharedValue(1);
  const isIconRound = variant === 'icon-round';
  const isDisabled = disabled || isLoading;

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }));

  const handlePressIn = () => {
    if (!isDisabled && !isIconRound) scale.value = withSpring(0.96);
  };
  const handlePressOut = () => {
    if (!isDisabled && !isIconRound) scale.value = withSpring(1);
  };

  const { container, textColor } = getButtonStyles(variant, isDisabled);

  return (
    <AnimatedTouchable
      onPress={onPress}
      onPressIn={handlePressIn}
      onPressOut={handlePressOut}
      disabled={isDisabled}
      activeOpacity={isDisabled ? 1 : isIconRound ? 0.75 : 0.9}
      style={[
        isIconRound ? styles.iconRound : styles.base,
        container,
        style,
        animatedStyle,
      ]}
    >
      {isLoading ? (
        <ActivityIndicator color={textColor} />
      ) : isIconRound ? (
        icon
      ) : (
        <Text style={[Typography.button, { color: textColor }]}>{title}</Text>
      )}
    </AnimatedTouchable>
  );
}

const styles = StyleSheet.create({
  base: {
    paddingVertical: 14,
    paddingHorizontal: 24,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 8,
    minHeight: 52,
  },
  iconRound: {
    alignItems: 'center',
    justifyContent: 'center',
  },
});
