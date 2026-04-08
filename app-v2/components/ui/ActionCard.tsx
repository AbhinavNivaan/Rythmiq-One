import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { LucideIcon } from 'lucide-react-native';
import Colors from '../../constants/Colors';
import Animated, { useAnimatedStyle, useSharedValue, withSpring } from 'react-native-reanimated';

type IconComponent = LucideIcon | React.ComponentType<{ size?: number; color?: string }>;

interface ActionCardProps {
    title: string;
    description: string;
    icon: IconComponent;
    onPress: () => void;
    disabled?: boolean;
}

const AnimatedTouchable = Animated.createAnimatedComponent(TouchableOpacity);

export default function ActionCard({ title, description, icon: Icon, onPress, disabled }: ActionCardProps) {
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

    return (
        <AnimatedTouchable
            onPress={onPress}
            onPressIn={disabled ? undefined : handlePressIn}
            onPressOut={disabled ? undefined : handlePressOut}
            activeOpacity={disabled ? 0.7 : 0.9}
            style={[styles.container, disabled && styles.containerDisabled, animatedStyle]}
        >
            <View style={styles.iconContainer}>
                <Icon size={28} color={disabled ? '#555' : Colors.palette.white} />
            </View>
            <View style={styles.content}>
                <Text style={[styles.title, disabled && styles.titleDisabled]}>{title}</Text>
                <Text style={styles.description} numberOfLines={2}>{description}</Text>
            </View>
            {disabled && (
                <View style={styles.comingSoonBadge}>
                    <Text style={styles.comingSoonText}>Coming soon</Text>
                </View>
            )}
        </AnimatedTouchable>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: Colors.palette.shadowGrey,
        borderRadius: 24,
        padding: 16,
        minHeight: 140,
        justifyContent: 'space-between',
        borderWidth: 1,
        borderColor: 'rgba(255, 255, 255, 0.05)',
        // Slight shadow for depth
        shadowColor: "#000",
        shadowOffset: {
            width: 0,
            height: 4,
        },
        shadowOpacity: 0.2,
        shadowRadius: 5.46,
        elevation: 9,
    },
    iconContainer: {
        width: 48,
        height: 48,
        borderRadius: 14,
        backgroundColor: 'rgba(255, 255, 255, 0.1)', // Glassy icon background
        alignItems: 'center',
        justifyContent: 'center',
        marginBottom: 12,
    },
    content: {
        gap: 4,
    },
    title: {
        fontSize: 18,
        fontWeight: 'bold',
        color: Colors.palette.white,
    },
    description: {
        fontSize: 12,
        color: '#999',
        lineHeight: 16,
    },
    containerDisabled: {
        opacity: 0.65,
    },
    titleDisabled: {
        color: '#666',
    },
    comingSoonBadge: {
        position: 'absolute',
        top: 12,
        right: 12,
        backgroundColor: 'rgba(255, 255, 255, 0.08)',
        borderRadius: 8,
        paddingHorizontal: 8,
        paddingVertical: 3,
        borderWidth: 1,
        borderColor: 'rgba(255, 255, 255, 0.1)',
    },
    comingSoonText: {
        fontSize: 10,
        color: '#666',
        fontWeight: '500',
    },
});
