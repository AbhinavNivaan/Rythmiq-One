import { StyleSheet, Text, View, TouchableOpacity, Image } from 'react-native';
import { Link, router } from 'expo-router';
import Colors from '../../constants/Colors';
import Input from '../../components/ui/Input';
import Button from '../../components/ui/Button';
import Logo from '../../components/ui/Logo';
import AdaptiveScreen from '../../components/ui/AdaptiveScreen';
import { Mail, Lock, User, Zap } from 'lucide-react-native';
import { useState } from 'react';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { useAuth } from '../../contexts/AuthContext';
import { isValidEmail, validatePassword } from '../../utils/helpers';

export default function SignupScreen() {
    const [name, setName] = useState('');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');
    const [info, setInfo] = useState('');
    const { signup } = useAuth();

    const handleSignup = async () => {
        setError('');
        setInfo('');
        
        // Validation
        if (!name || !email || !password || !confirmPassword) {
            setError('Please fill in all fields');
            return;
        }
        
        if (!isValidEmail(email)) {
            setError('Please enter a valid email');
            return;
        }
        
        const passwordCheck = validatePassword(password);
        if (!passwordCheck.valid) {
            setError(passwordCheck.message);
            return;
        }
        
        if (password !== confirmPassword) {
            setError('Passwords do not match');
            return;
        }

        setIsLoading(true);
        try {
            await signup(email, password, name);
            router.replace('/(tabs)/dashboard');
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : 'Signup failed';
            if (errorMessage.toLowerCase().includes('verify your account')) {
                setInfo(errorMessage);
                router.replace('/(auth)/login');
                return;
            }
            setError(errorMessage);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <AdaptiveScreen contentContainerStyle={styles.contentContainer}>

            <Animated.View entering={FadeInDown.duration(800).springify()} style={styles.logoSection}>
                <Logo size={55} color="#FFFFFF" />
            </Animated.View>

            <View style={styles.bottomSection}>
                <Animated.View entering={FadeInDown.delay(200).duration(800).springify()} style={styles.header}>
                    <Text style={styles.title}>Sign Up</Text>
                    <Text style={styles.subtitle}>Use proper information to continue</Text>
                </Animated.View>

                <Animated.View entering={FadeInDown.delay(400).duration(800).springify()} style={styles.form}>
                    {info ? (
                        <View style={styles.infoContainer}>
                            <Text style={styles.infoText}>{info}</Text>
                        </View>
                    ) : null}
                    {error ? (
                        <View style={styles.errorContainer}>
                            <Text style={styles.errorText}>{error}</Text>
                        </View>
                    ) : null}
                    <Input
                        placeholder="Full name"
                        icon={User}
                        autoCapitalize="words"
                        value={name}
                        onChangeText={setName}
                    />
                    <Input
                        placeholder="Email address"
                        icon={Mail}
                        keyboardType="email-address"
                        autoCapitalize="none"
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
                    <Input
                        placeholder="Confirm password"
                        icon={Lock}
                        secureTextEntry
                        value={confirmPassword}
                        onChangeText={setConfirmPassword}
                    />

                    <Text style={styles.termsText}>
                        By signing up, you are agree to our <Text style={styles.linkText}>Terms & Conditions</Text> and <Text style={styles.linkText}>Privacy Policy</Text>
                    </Text>

                    <Button
                        title="Create Account"
                        onPress={handleSignup}
                        isLoading={isLoading}
                        variant="primary-white"
                        style={styles.signupButton}
                    />
                </Animated.View>

                <Animated.View entering={FadeInDown.delay(600).duration(800).springify()} style={styles.footer}>
                    <Text style={styles.footerText}>Already have an account? </Text>
                    <Link href="/(auth)/login" asChild>
                        <TouchableOpacity>
                            <Text style={styles.loginText}>Sign in</Text>
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
        marginBottom: 18,
    },
    bottomSection: {
        width: '100%',
        gap: 10,
        alignItems: 'center',
    },
    header: {
        alignItems: 'center',
        width: '100%',
        marginBottom: 2,
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
        gap: 8,
        alignItems: 'center',
    },
    termsText: {
        fontSize: 11,
        color: '#999',
        textAlign: 'center',
        marginVertical: 4,
        lineHeight: 16,
        paddingHorizontal: 12,
    },
    linkText: {
        color: '#89C7FE',
        fontWeight: 'bold',
    },
    signupButton: {
        width: '100%',
        marginTop: 2,
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
    loginText: {
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
        marginBottom: 2,
    },
    errorText: {
        color: '#ef4444',
        fontSize: 12,
        textAlign: 'center',
    },
    infoContainer: {
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        padding: 10,
        borderRadius: 6,
        borderWidth: 1,
        borderColor: 'rgba(59, 130, 246, 0.3)',
        marginBottom: 2,
    },
    infoText: {
        color: '#60a5fa',
        fontSize: 12,
        textAlign: 'center',
    },
    devButton: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 6,
        marginTop: 6,
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
});
