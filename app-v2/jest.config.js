module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  extensionsToTreatAsEsm: ['.ts', '.tsx'],
  globals: {
    'ts-jest': {
      useESM: true,
      tsconfig: {
        esModuleInterop: true,
        allowSyntheticDefaultImports: true,
        jsx: 'react',
      },
    },
  },
  transform: {
    '^.+\\.m?tsx?$': ['ts-jest', { useESM: true, tsconfig: { esModuleInterop: true, allowSyntheticDefaultImports: true, jsx: 'react' } }],
  },
  moduleNameMapper: {
    '\\.tflite$': '<rootDir>/__mocks__/fileMock.js',
    '^expo(/.*)?$': '<rootDir>/__mocks__/expo.js',
    '^expo-secure-store$': '<rootDir>/__mocks__/expo-secure-store.js',
    '^expo-web-browser$': '<rootDir>/__mocks__/expo-web-browser.js',
    '^expo-auth-session$': '<rootDir>/__mocks__/expo-auth-session.js',
    '^@supabase/supabase-js$': '<rootDir>/__mocks__/supabase.js',
    '^react-native(/.*)?$': '<rootDir>/__mocks__/react-native.js',
    '^react-native-reanimated(/.*)?$': '<rootDir>/__mocks__/react-native-reanimated.js',
    '^lucide-react-native$': '<rootDir>/__mocks__/lucide-react-native.js',
  },
  collectCoverageFrom: [
    'services/**/*.ts',
    '!**/__tests__/**',
  ],
  testMatch: [
    '**/__tests__/**/*.test.ts',
  ],
  transformIgnorePatterns: [
    'node_modules/(?!(expo|@expo|react-native|react-native-reanimated|@supabase|@react-native)/)',
  ],
};
