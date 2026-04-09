import { Redirect, Stack } from 'expo-router';
import { useSessionGate } from '../../hooks/useSessionGate';

export default function TabLayout() {
    const gate = useSessionGate();

    // Hold while auth resolves
    if (gate.isLoading) return null;

    // Unauthenticated — send to login
    if (!gate.ready) return <Redirect href="/(auth)/login" />;

    return (
        <Stack
            screenOptions={{
                headerShown: false,
            }}
        >
            <Stack.Screen name="dashboard" />
            <Stack.Screen name="jobs" />
            <Stack.Screen name="capture" />
            <Stack.Screen name="upload" />
            <Stack.Screen name="job-detail" />
            <Stack.Screen name="portal-selector" />
            <Stack.Screen name="adapt-status" />
            <Stack.Screen name="error-report" />
            <Stack.Screen name="document-viewer" />
        </Stack>
    );
}
