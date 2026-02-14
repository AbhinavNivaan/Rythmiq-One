import React from 'react';
import { StyleSheet, View, ViewStyle } from 'react-native';
import Colors from '../../constants/Colors';

interface CardProps {
    children: React.ReactNode;
    style?: ViewStyle;
    variant?: 'default' | 'elevated' | 'glass';
}

export default function Card({ children, style, variant = 'default' }: CardProps) {
    const getBackgroundColor = () => {
        switch (variant) {
            case 'default':
                return Colors.palette.shadowGrey; // '#191B26'
            case 'elevated':
                return '#23263a'; // Slightly lighter than shadow grey for elevation
            case 'glass':
                return 'rgba(25, 27, 38, 0.7)'; // Translucent Shadow Grey
            default:
                return Colors.palette.shadowGrey;
        }
    };

    const getBorder = () => {
        // The reference card has a very subtle border or separation
        return {
            borderWidth: 1,
            borderColor: 'rgba(255, 255, 255, 0.05)',
        };
    };

    return (
        <View style={[
            styles.container,
            { backgroundColor: getBackgroundColor() },
            getBorder(),
            style
        ]}>
            {children}
        </View>
    );
}

const styles = StyleSheet.create({
    container: {
        borderRadius: 24, // Matching the large rounded corners from the reference
        padding: 20,
        width: '100%',
        // Shadow for depth ( subtle for dark mode)
        shadowColor: '#000',
        shadowOffset: {
            width: 0,
            height: 4,
        },
        shadowOpacity: 0.3,
        shadowRadius: 8,
        elevation: 5,
    },
});
