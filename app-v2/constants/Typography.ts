import { TextStyle } from 'react-native';

const Typography: Record<string, TextStyle> = {
  nano: {
    fontFamily: 'Satoshi-Medium',
    fontSize: 10,
    lineHeight: 14,
  },
  caption: {
    fontFamily: 'Satoshi-Regular',
    fontSize: 12,
    lineHeight: 16,
  },
  label: {
    fontFamily: 'Satoshi-Medium',
    fontSize: 14,
    lineHeight: 20,
  },
  body: {
    fontFamily: 'Satoshi-Regular',
    fontSize: 16,
    lineHeight: 24,
  },
  button: {
    fontFamily: 'Satoshi-Bold',
    fontSize: 16,
    letterSpacing: 0.3,
  },
  titleSm: {
    fontFamily: 'Satoshi-Bold',
    fontSize: 20,
    lineHeight: 28,
  },
  titleMd: {
    fontFamily: 'Satoshi-Bold',
    fontSize: 24,
    lineHeight: 32,
  },
  titleLg: {
    fontFamily: 'Satoshi-Black',
    fontSize: 32,
    lineHeight: 40,
  },
};

export default Typography;
