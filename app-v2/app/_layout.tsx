import { DarkTheme, DefaultTheme, ThemeProvider } from '@react-navigation/native';
import { useFonts } from 'expo-font';
import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';
import { StatusBar } from 'expo-status-bar';
import 'react-native-reanimated';
import { useColorScheme } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { AuthProvider, useAuth } from '../contexts/AuthContext';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

SplashScreen.preventAutoHideAsync();

const queryClient = new QueryClient({
    defaultOptions: {
        queries: {
            staleTime: 1000 * 60 * 5,
            retry: 2,
        },
    },
});

// Inner component so it can read AuthContext
function AppShell() {
    const colorScheme = useColorScheme();
    const [fontsLoaded] = useFonts({});
    const { isLoading: authLoading } = useAuth();

    useEffect(() => {
        if (fontsLoaded && !authLoading) {
            SplashScreen.hideAsync();
        }
    }, [fontsLoaded, authLoading]);

    if (!fontsLoaded) {
        return null;
    }

    const theme = colorScheme === 'dark' ? DarkTheme : DefaultTheme;

    return (
        <ThemeProvider value={theme}>
            <Stack>
                <Stack.Screen name="index" options={{ headerShown: false }} />
                <Stack.Screen name="onboarding" options={{ headerShown: false }} />
                <Stack.Screen name="(auth)" options={{ headerShown: false }} />
                <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
                <Stack.Screen name="+not-found" />
            </Stack>
            <StatusBar style="auto" />
        </ThemeProvider>
    );
}

export default function RootLayout() {
    return (
        <GestureHandlerRootView style={{ flex: 1 }}>
            <QueryClientProvider client={queryClient}>
                <AuthProvider>
                    <AppShell />
                </AuthProvider>
            </QueryClientProvider>
        </GestureHandlerRootView>
    );
}
