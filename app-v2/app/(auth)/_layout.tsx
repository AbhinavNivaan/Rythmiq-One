import { Redirect, Stack } from 'expo-router';
import { useAuth } from '../../contexts/AuthContext';

export default function AuthLayout() {
    const { isAuthenticated, isLoading } = useAuth();

    // Hold while auth resolves — prevents flash of login screen for returning users
    if (isLoading) return null;

    // Already logged in — push straight to dashboard
    if (isAuthenticated) return <Redirect href="/(tabs)/dashboard" />;

    return (
        <Stack screenOptions={{ headerShown: false, animation: 'fade' }}>
            <Stack.Screen name="login" />
            <Stack.Screen name="signup" />
        </Stack>
    );
}
