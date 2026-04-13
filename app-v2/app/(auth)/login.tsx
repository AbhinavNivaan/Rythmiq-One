import { StyleSheet, Text, View, TouchableOpacity } from 'react-native';
import { Link, router } from 'expo-router';
import Colors from '../../constants/Colors';
import Input from '../../components/ui/Input';
import Button from '../../components/ui/Button';
import Logo from '../../components/ui/Logo';
import GoogleIcon from '../../components/ui/GoogleIcon';
import AppleIcon from '../../components/ui/AppleIcon';
import AdaptiveScreen from '../../components/ui/AdaptiveScreen';
import { Mail, Lock, Zap } from 'lucide-react-native';
import { useState } from 'react';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { useAuth } from '../../contexts/AuthContext';
import { isValidEmail } from '../../utils/helpers';

export default function LoginScreen() {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');
    const { login, loginWithGoogle, loginWithApple } = useAuth();

    const handleLogin = async () => {
        setError('');
        
        // Validation
        if (!email || !password) {
            setError('Please fill in all fields');
            return;
        }
        
        if (!isValidEmail(email)) {
            setError('Please enter a valid email');
            return;
        }

        setIsLoading(true);
        try {
            await login(email, password);
            router.replace('/(tabs)/dashboard');
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : 'Login failed';
            setError(errorMessage);
        } finally {
            setIsLoading(false);
        }
    };

    const handleGoogleLogin = async () => {
        setError('');
        setIsLoading(true);
        try {
            await loginWithGoogle();
            router.replace('/(tabs)/dashboard');
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : 'Google login failed';
            setError(errorMessage);
        } finally {
            setIsLoading(false);
        }
    };

    const handleAppleLogin = async () => {
        setError('');
        setIsLoading(true);
        try {
            await loginWithApple();
            router.replace('/(tabs)/dashboard');
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : 'Apple login failed';
            setError(errorMessage);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <AdaptiveScreen contentContainerStyle={styles.contentContainer}>

            {/* Logo Section */}
            <Animated.View entering={FadeInDown.duration(800).springify()} style={styles.logoSection}>
                <Logo size={60} color="#FFFFFF" />
            </Animated.View>

            {/* Bottom Content Section - Fixed/Content Based */}
            <View style={styles.bottomSection}>
                <Animated.View entering={FadeInDown.delay(200).duration(800).springify()} style={styles.header}>
                    <Text style={styles.title}>Sign In</Text>
                    <Text style={styles.subtitle}>Enter valid user name & password to continue</Text>
                </Animated.View>

                <Animated.View entering={FadeInDown.delay(400).duration(800).springify()} style={styles.form}>
                    {error ? (
                        <View style={styles.errorContainer}>
                            <Text style={styles.errorText}>{error}</Text>
                        </View>
                    ) : null}
                    <Input
                        placeholder="Email address"
                        icon={Mail}
                        autoCapitalize="none"
                        keyboardType="email-address"
                        value={email}
                        onChangeText={setEmail}
                    />
                    <Input
                        placeholder="Password"
                        icon={Lock}
                        secureTextEntry
                        value={password}
                        onChangeText={setPassword}
                    />

                    <Button
                        title="Login"
                        onPress={handleLogin}
                        isLoading={isLoading}
                        variant="primary-white"
                        style={styles.loginButton}
                    />
                </Animated.View>

                <Animated.View entering={FadeInDown.delay(600).duration(800).springify()} style={styles.socialSection}>
                    <View style={styles.dividerContainer}>
                        <View style={styles.divider} />
                        <Text style={styles.dividerText}>Or Continue with</Text>
                        <View style={styles.divider} />
                    </View>

                    <View style={styles.socialButtons}>
                        <TouchableOpacity
                            style={[styles.socialButton, styles.googleButton]}
                            onPress={handleGoogleLogin}
                            disabled={isLoading}
                        >
                            <GoogleIcon size={24} />
                        </TouchableOpacity>
                        <TouchableOpacity
                            style={[styles.socialButton, styles.appleButton]}
                            onPress={handleAppleLogin}
                            disabled={isLoading}
                        >
                            <AppleIcon size={24} />
                        </TouchableOpacity>
                    </View>
                </Animated.View>

                <Animated.View entering={FadeInDown.delay(800).duration(800).springify()} style={styles.footer}>
                    <Text style={styles.footerText}>Haven't any account? </Text>
                    <Link href="/(auth)/signup" asChild>
                        <TouchableOpacity>
                            <Text style={styles.signupText}>Sign up</Text>
                        </TouchableOpacity>
                    </Link>
                </Animated.View>

                {__DEV__ && (
                    <TouchableOpacity 
                        style={styles.devButton}
                        onPress={() => router.replace('/(tabs)/dashboard')}
                    >
                        <Zap size={16} color="#FFD700" />
                        <Text style={styles.devButtonText}>Dev Mode</Text>
                    </TouchableOpacity>
                )}
            </View>
        </AdaptiveScreen>
    );
}

const styles = StyleSheet.create({
    contentContainer: {
        flexGrow: 1,
        justifyContent: 'center',
        alignItems: 'center',
        paddingHorizontal: 16,
        paddingBottom: 12,
    },
    logoSection: {
        justifyContent: 'center',
        alignItems: 'center',
        marginBottom: 20,
    },
    bottomSection: {
        width: '100%',
        gap: 12,
        alignItems: 'center',
    },
    header: {
        alignItems: 'center',
        width: '100%',
        marginBottom: 4,
    },
    title: {
        fontSize: 24,
        fontWeight: 'bold',
        color: Colors.palette.white,
        marginBottom: 4,
    },
    subtitle: {
        fontSize: 12,
        color: '#999',
        textAlign: 'center',
    },
    form: {
        width: '100%',
        gap: 10,
        alignItems: 'center',
    },
    loginButton: {
        width: '100%',
        marginTop: 4,
    },
    socialSection: {
        width: '100%',
        gap: 10,
        alignItems: 'center',
    },
    dividerContainer: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
    },
    divider: {
        height: 1,
        flex: 1,
        backgroundColor: 'rgba(255, 255, 255, 0.1)',
    },
    dividerText: {
        color: '#666',
        fontSize: 11,
        marginHorizontal: 12,
    },
    socialButtons: {
        flexDirection: 'row',
        gap: 12,
        justifyContent: 'center',
    },
    socialButton: {
        width: 48,
        height: 48,
        alignItems: 'center',
        justifyContent: 'center',
        borderRadius: 12,
    },
    googleButton: {
        backgroundColor: '#FFFFFF',
    },
    appleButton: {
        backgroundColor: '#000000',
        borderWidth: 1,
        borderColor: 'rgba(255, 255, 255, 0.2)',
    },
    socialIcon: {
        width: 24,
        height: 24,
    },
    footer: {
        flexDirection: 'row',
        justifyContent: 'center',
        alignItems: 'center',
        marginTop: 4,
    },
    footerText: {
        color: '#999',
        fontSize: 12,
    },
    signupText: {
        color: '#89C7FE',
        fontSize: 12,
        fontWeight: 'bold',
    },
    errorContainer: {
        backgroundColor: 'rgba(239, 68, 68, 0.1)',
        padding: 10,
        borderRadius: 6,
        borderWidth: 1,
        borderColor: 'rgba(239, 68, 68, 0.3)',
        marginBottom: 4,
    },
    errorText: {
        color: '#ef4444',
        fontSize: 12,
        textAlign: 'center',
    },
    devButton: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 6,
        marginTop: 8,
        paddingVertical: 8,
        paddingHorizontal: 12,
        borderRadius: 6,
        backgroundColor: 'rgba(255, 215, 0, 0.1)',
        borderWidth: 1,
        borderColor: 'rgba(255, 215, 0, 0.3)',
    },
    devButtonText: {
        color: '#FFD700',
        fontSize: 11,
        fontWeight: '600',
    },
    devRedirectText: {
        color: '#666',
        fontSize: 10,
        textAlign: 'center',
    },
});
