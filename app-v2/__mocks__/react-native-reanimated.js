// Mock for react-native-reanimated
// With esModuleInterop, `import Animated from 'react-native-reanimated'`
// resolves to module.exports itself as the default.

const createAnimatedComponent = (Component) => Component;

const Animated = {
  createAnimatedComponent,
  View: 'Animated.View',
  Text: 'Animated.Text',
  ScrollView: 'Animated.ScrollView',
  FlatList: 'Animated.FlatList',
  Image: 'Animated.Image',
  TouchableOpacity: 'Animated.TouchableOpacity',
};

// Named exports
const useAnimatedStyle = (fn) => { try { return fn(); } catch { return {}; } };
const useSharedValue = (initial) => ({ value: initial });
const withSpring = (value) => value;
const withTiming = (value) => value;
const runOnJS = (fn) => fn;
const interpolate = (value, input, output) => output[0];
const Extrapolation = { CLAMP: 'clamp' };

// The default export IS the Animated object.
// For CJS interop, we attach everything to module.exports
// so that `import Animated from '...'` === module.exports
// and named imports also work.
module.exports = Animated;
module.exports.default = Animated;
module.exports.useAnimatedStyle = useAnimatedStyle;
module.exports.useSharedValue = useSharedValue;
module.exports.withSpring = withSpring;
module.exports.withTiming = withTiming;
module.exports.runOnJS = runOnJS;
module.exports.interpolate = interpolate;
module.exports.Extrapolation = Extrapolation;
module.exports.plugin = {};
