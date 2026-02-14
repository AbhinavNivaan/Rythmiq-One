import React from 'react';
import { StyleSheet, View, KeyboardAvoidingView, Platform, ScrollView, ViewStyle } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Colors from '../../constants/Colors';

interface AdaptiveScreenProps {
    children: React.ReactNode;
    style?: ViewStyle;
    contentContainerStyle?: ViewStyle;
}

/**
 * AdaptiveScreen
 * 
 * A reusable wrapper for single-page forms/content.
 * Designed to fit content on one screen without scrolling by default,
 * but adapts for smaller screens or keyboard presence.
 * 
 * Layout Strategy:
 * - Uses Flexbox (flex: 1) to fill the screen.
 * - contentContainerStyle should handle distribution (e.g., justifyContent: 'space-between').
 * - KeyboardAvoidingView ensures inputs aren't hidden.
 * - ScrollView is present but behaves like a View (scrollEnabled only when necessary implicitly by layout).
 */
export default function AdaptiveScreen({ children, style, contentContainerStyle }: AdaptiveScreenProps) {
    return (
        <SafeAreaView style={[styles.container, style]}>
            <KeyboardAvoidingView
                behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
                style={styles.keyboardAvoidingView}
            >
                <ScrollView
                    contentContainerStyle={[styles.scrollContent, contentContainerStyle]}
                    showsVerticalScrollIndicator={false}
                    bounces={false}
                    keyboardShouldPersistTaps="handled"
                >
                    {children}
                </ScrollView>
            </KeyboardAvoidingView>
        </SafeAreaView>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: Colors.palette.inkBlack,
    },
    keyboardAvoidingView: {
        flex: 1,
    },
    scrollContent: {
        flexGrow: 1,
        // Default layout strategy:
        // Users can override this to 'center' or 'space-between'
    },
});
