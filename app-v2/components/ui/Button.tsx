import React from 'react';
import { StyleSheet, Text, TouchableOpacity, ActivityIndicator, ViewStyle, TextStyle } from 'react-native';
import { Sparkles } from 'lucide-react-native';
import Colors from '../../constants/Colors';
import Animated, { useAnimatedStyle, useSharedValue, withSpring } from 'react-native-reanimated';

interface ButtonProps {
    onPress: () => void;
    title: string;
    variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'dark';
    isLoading?: boolean;
    style?: ViewStyle;
    textStyle?: TextStyle;
    disabled?: boolean;
    icon?: React.ReactNode;
    showIcon?: boolean;
}

const AnimatedTouchable = Animated.createAnimatedComponent(TouchableOpacity);

export default function Button({
    onPress,
    title,
    variant = 'primary',
    isLoading = false,
    style,
    textStyle,
    disabled = false,
    icon,
    showIcon = false,
}: ButtonProps) {
    const scale = useSharedValue(1);

    const animatedStyle = useAnimatedStyle(() => {
        return {
            transform: [{ scale: scale.value }],
        };
    });

    const handlePressIn = () => {
        scale.value = withSpring(0.96);
    };

    const handlePressOut = () => {
        scale.value = withSpring(1);
    };

    const getBackgroundColor = () => {
        if (disabled) return '#A0A0A0';
        switch (variant) {
            case 'primary': // White background for primary CTAs
                return Colors.palette.white;
            case 'secondary': // Dark with outline
                return 'transparent';
            case 'dark': // Ink Black (legacy, might deprecate)
                return Colors.palette.inkBlack;
            case 'outline':
                return 'transparent';
            case 'ghost':
                return 'transparent';
            default:
                return Colors.palette.white; // Default to white
        }
    };

    const getTextColor = () => {
        if (disabled) return '#F0F0F0';
        switch (variant) {
            case 'primary': // Dark text on white
                return Colors.palette.inkBlack;
            case 'secondary': // Light text on dark
            case 'outline':
            case 'ghost':
                return Colors.palette.white;
            case 'dark':
                return '#FFFFFF';
            default:
                return Colors.palette.inkBlack; // Default dark text
        }
    };

    const getBorder = () => {
        if (variant === 'secondary') {
            return {
                borderWidth: 1.5,
                borderColor: 'rgba(255, 255, 255, 0.3)' // Light outline for secondary
            };
        }
        if (variant === 'outline') {
            return { borderWidth: 1, borderColor: '#E5E7EB' };
        }
        return {};
    };

    // Shadow/3D effect from the middle row of the reference image
    const getShadow = () => {
        if (variant === 'primary' || variant === 'dark') {
            return {
                borderBottomWidth: 4,
                borderBottomColor: variant === 'primary' ? '#141c7a' : '#000000', // Darker shade
            }
        }
        return {};
    }

    const textColor = getTextColor();

    return (
        <AnimatedTouchable
            onPress={onPress}
            onPressIn={handlePressIn}
            onPressOut={handlePressOut}
            disabled={disabled || isLoading}
            activeOpacity={0.9}
            style={[
                styles.container,
                { backgroundColor: getBackgroundColor() },
                getBorder(),
                // getShadow(), // Uncomment if we want the 3D 'pressed' look permanent, otherwise just use flat
                style,
                animatedStyle,
            ]}
        >
            {isLoading ? (
                <ActivityIndicator color={textColor} />
            ) : (
                <>
                    {showIcon && icon}
                    <Text style={[styles.text, { color: textColor }, textStyle]}>{title}</Text>
                </>
            )}
        </AnimatedTouchable>
    );
}

const styles = StyleSheet.create({
    container: {
        paddingVertical: 14,
        paddingHorizontal: 24,
        borderRadius: 12,
        alignItems: 'center',
        justifyContent: 'center',
        flexDirection: 'row',
        gap: 8,
        minHeight: 52,
    },
    text: {
        fontSize: 16,
        fontWeight: '600',
        letterSpacing: 0.3,
    },
    icon: {
        opacity: 0.9,
    }
});
