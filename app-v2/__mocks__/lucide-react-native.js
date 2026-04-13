// Mock for lucide-react-native — prevents SVG/react-native-svg issues in Jest
const React = require('react');

const createIcon = (name) => {
  const Icon = () => null;
  Icon.displayName = name;
  return Icon;
};

module.exports = new Proxy(
  {},
  {
    get(target, prop) {
      if (prop === '__esModule') return true;
      return createIcon(String(prop));
    },
  }
);
