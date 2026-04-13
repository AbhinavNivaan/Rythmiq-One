import React, { useState } from 'react';
import { StyleSheet, TextInput, View, Text, TextInputProps, TouchableOpacity, ViewStyle } from 'react-native';
import { LucideIcon, Eye, EyeOff } from 'lucide-react-native';
import Colors from '../../constants/Colors';
import Typography from '../../constants/Typography';

interface InputStateProps {
  focused: boolean;
  error: boolean;
  disabled: boolean;
}

interface InputStyleResult {
  container: ViewStyle;
  iconColor: string;
  textColor: string;
  placeholderColor: string;
}

export function getInputStyles({ focused, error, disabled }: InputStateProps): InputStyleResult {
  if (disabled) {
    return {
      container: {
        backgroundColor: Colors.palette.neutral0,
        borderWidth: 1.5,
        borderStyle: 'dashed',
        borderColor: 'rgba(252,254,255,0.12)',
      },
      iconColor: 'rgba(252,254,255,0.15)',
      textColor: 'rgba(252,254,255,0.20)',
      placeholderColor: 'rgba(252,254,255,0.15)',
    };
  }
  if (error) {
    return {
      container: {
        backgroundColor: Colors.semantic.surface,
        borderWidth: 1.5,
        borderStyle: 'solid',
        borderColor: Colors.semantic.borderError,
      },
      iconColor: Colors.palette.red,
      textColor: Colors.semantic.textPrimary,
      placeholderColor: 'rgba(252,254,255,0.40)',
    };
  }
  if (focused) {
    return {
      container: {
        backgroundColor: Colors.semantic.surfaceElevated,
        borderWidth: 1.5,
        borderStyle: 'solid',
        borderColor: Colors.semantic.borderFocus,
      },
      iconColor: Colors.semantic.accent,
      textColor: Colors.semantic.textPrimary,
      placeholderColor: 'rgba(252,254,255,0.40)',
    };
  }
  return {
    container: {
      backgroundColor: Colors.semantic.surface,
      borderWidth: 1,
      borderStyle: 'solid',
      borderColor: Colors.semantic.borderSubtle,
    },
    iconColor: 'rgba(252,254,255,0.30)',
    textColor: Colors.semantic.textPrimary,
    placeholderColor: 'rgba(252,254,255,0.40)',
  };
}

interface InputProps extends TextInputProps {
  label?: string;
  icon?: LucideIcon;
  error?: string;
  disabled?: boolean;
}

export default function Input({
  label,
  icon: Icon,
  error,
  disabled = false,
  style,
  onFocus,
  onBlur,
  secureTextEntry,
  ...props
}: InputProps) {
  const [focused, setIsFocused] = useState(false);
  const [passwordVisible, setPasswordVisible] = useState(false);

  const inputStyles = getInputStyles({ focused, error: !!error, disabled });

  return (
    <View style={[baseStyles.wrapper, style]}>
      {label && (
        <Text style={[Typography.label, { color: Colors.semantic.textPrimary, marginBottom: 8, marginLeft: 4 }]}>
          {label}
        </Text>
      )}
      <View style={[baseStyles.row, inputStyles.container]}>
        {Icon && (
          <View style={baseStyles.iconWrap}>
            <Icon size={20} color={inputStyles.iconColor} />
          </View>
        )}
        <TextInput
          style={[baseStyles.input, { color: inputStyles.textColor }]}
          placeholderTextColor={inputStyles.placeholderColor}
          editable={!disabled}
          onFocus={(e) => { setIsFocused(true); onFocus?.(e); }}
          onBlur={(e) => { setIsFocused(false); onBlur?.(e); }}
          secureTextEntry={secureTextEntry && !passwordVisible}
          {...props}
        />
        {secureTextEntry && !disabled && (
          <TouchableOpacity
            style={baseStyles.eyeWrap}
            onPress={() => setPasswordVisible(v => !v)}
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            {passwordVisible
              ? <EyeOff size={18} color={Colors.semantic.textSecondary} />
              : <Eye size={18} color={Colors.semantic.textSecondary} />
            }
          </TouchableOpacity>
        )}
      </View>
      {error && (
        <Text style={[Typography.caption, { color: Colors.semantic.textError, marginTop: 4, marginLeft: 4 }]}>
          {error}
        </Text>
      )}
    </View>
  );
}

const baseStyles = StyleSheet.create({
  wrapper: { width: '100%' },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    height: 56,
    borderRadius: 16,
  },
  iconWrap: { paddingLeft: 16, paddingRight: 8 },
  eyeWrap: { paddingRight: 16, paddingLeft: 8 },
  input: {
    flex: 1,
    height: '100%',
    paddingHorizontal: 16,
    ...Typography.body,
  },
});
