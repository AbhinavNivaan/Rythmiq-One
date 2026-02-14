import { Stack } from 'expo-router';

export default function TabLayout() {
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
        </Stack>
    );
}
