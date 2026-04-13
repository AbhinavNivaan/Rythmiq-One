module.exports = {
  Platform: {
    OS: 'web',
  },
  StyleSheet: {
    create: (styles) => styles,
    flatten: (style) => style,
    hairlineWidth: 0.5,
  },
  Text: 'Text',
  View: 'View',
  TouchableOpacity: 'TouchableOpacity',
  ActivityIndicator: 'ActivityIndicator',
  ScrollView: 'ScrollView',
  FlatList: 'FlatList',
  Image: 'Image',
  TextInput: 'TextInput',
  Modal: 'Modal',
  Pressable: 'Pressable',
  SafeAreaView: 'SafeAreaView',
  KeyboardAvoidingView: 'KeyboardAvoidingView',
  Dimensions: {
    get: () => ({ width: 375, height: 812 }),
    addEventListener: () => ({ remove: () => {} }),
  },
  Animated: {
    Value: class { constructor(v) { this._value = v; } },
    timing: () => ({ start: (cb) => cb && cb({ finished: true }) }),
    spring: () => ({ start: (cb) => cb && cb({ finished: true }) }),
    createAnimatedComponent: (c) => c,
    View: 'Animated.View',
  },
  Alert: {
    alert: () => {},
  },
  Linking: {
    openURL: () => Promise.resolve(),
  },
};
