import React, { useState } from 'react';
import { StyleSheet, TextInput, View, Text, TextInputProps } from 'react-native';
import Colors from '../../constants/Colors';
import { LucideIcon } from 'lucide-react-native';

interface InputProps extends TextInputProps {
    label?: string;
    icon?: LucideIcon;
    error?: string;
}

export default function Input({ label, icon: Icon, error, style, onFocus, onBlur, ...props }: InputProps) {
    const [isFocused, setIsFocused] = useState(false);

    const handleFocus = (e: any) => {
        setIsFocused(true);
        onFocus?.(e);
    };

    const handleBlur = (e: any) => {
        setIsFocused(false);
        onBlur?.(e);
    };

    return (
        <View style={[styles.container, style]}>
            {label && <Text style={styles.label}>{label}</Text>}
            <View
                style={[
                    styles.inputContainer,
                    isFocused && styles.inputContainerFocused,
                    !!error && styles.inputContainerError,
                ]}
            >
                {Icon && (
                    <View style={styles.iconContainer}>
                        <Icon size={20} color={isFocused ? Colors.palette.mayaBlue : 'rgba(255, 255, 255, 0.5)'} />
                    </View>
                )}
                <TextInput
                    style={styles.input}
                    placeholderTextColor="rgba(255, 255, 255, 0.4)"
                    onFocus={handleFocus}
                    onBlur={handleBlur}
                    {...props}
                />
            </View>
            {error && <Text style={styles.errorText}>{error}</Text>}
        </View>
    );
}

const styles = StyleSheet.create({
    container: {
        marginBottom: 20,
        width: '100%',
    },
    label: {
        color: Colors.palette.white, // White label
        fontSize: 14,
        marginBottom: 8,
        marginLeft: 4,
        fontWeight: '500',
        opacity: 0.9,
    },
    inputContainer: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: Colors.palette.shadowGrey, // Using shadow grey for input bg
        borderWidth: 1,
        borderColor: 'rgba(255, 255, 255, 0.05)', // Subtle border
        borderRadius: 16, // Matching button radius loosely (slightly larger radius for inputs is modern)
        height: 56,
    },
    inputContainerFocused: {
        borderColor: Colors.palette.trueCobalt, // Focus color
        backgroundColor: '#1E202E', // Slightly lighter on focus
    },
    inputContainerError: {
        borderColor: '#EF4444',
    },
    iconContainer: {
        paddingLeft: 16,
        paddingRight: 8,
    },
    input: {
        flex: 1,
        color: Colors.palette.white,
        fontSize: 16,
        height: '100%',
        paddingHorizontal: 16,
    },
    errorText: {
        color: '#EF4444',
        fontSize: 12,
        marginTop: 4,
        marginLeft: 4,
    },
});
