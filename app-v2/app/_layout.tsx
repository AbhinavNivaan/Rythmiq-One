import { useFonts } from 'expo-font';
import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';
import { StatusBar } from 'expo-status-bar';
import 'react-native-reanimated';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { AuthProvider, useAuth } from '../contexts/AuthContext';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ToastProvider } from '../components/ui/Toast';

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
    const [fontsLoaded, fontError] = useFonts({
        'Satoshi-Regular': require('../assets/fonts/Satoshi-Regular.otf'),
        'Satoshi-Medium':  require('../assets/fonts/Satoshi-Medium.otf'),
        'Satoshi-Bold':    require('../assets/fonts/Satoshi-Bold.otf'),
        'Satoshi-Black':   require('../assets/fonts/Satoshi-Black.otf'),
    });
    const { isLoading: authLoading } = useAuth();

    useEffect(() => {
        if (fontError) {
            throw fontError;
        }
        if (fontsLoaded && !authLoading) {
            SplashScreen.hideAsync();
        }
    }, [fontsLoaded, fontError, authLoading]);

    return (
        <ToastProvider>
            <Stack>
                <Stack.Screen name="index" options={{ headerShown: false }} />
                <Stack.Screen name="onboarding" options={{ headerShown: false }} />
                <Stack.Screen name="(auth)" options={{ headerShown: false }} />
                <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
                <Stack.Screen name="+not-found" />
            </Stack>
            <StatusBar style="auto" />
        </ToastProvider>
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
