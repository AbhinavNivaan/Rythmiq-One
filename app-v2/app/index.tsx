import { StyleSheet, Text, View, TouchableOpacity, Image } from 'react-native';
import { Link } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import { BlurView } from 'expo-blur';
import { SafeAreaView } from 'react-native-safe-area-context';
import Colors from '../constants/Colors';
import Animated, { FadeInDown, FadeInUp } from 'react-native-reanimated';

export default function WelcomeScreen() {
    return (
        <View style={styles.container}>
            <LinearGradient
                // Background Gradient
                colors={['#0f0c29', '#302b63', '#24243e']}
                start={{ x: 0, y: 0 }}
                end={{ x: 1, y: 1 }}
                style={styles.background}
            />

            <SafeAreaView style={styles.safeArea}>
                <View style={styles.contentContainer}>
                    <Animated.View entering={FadeInUp.delay(200).duration(1000)} style={styles.heroSection}>
                        <Text style={styles.title}>Rythmiq</Text>
                        <Text style={styles.titleAccent}>One</Text>
                    </Animated.View>

                    <Animated.View entering={FadeInDown.delay(400).duration(1000)} style={styles.cardContainer}>
                        <BlurView intensity={40} tint="dark" style={styles.card}>
                            <Text style={styles.tagline}>Premium Document Intelligence</Text>
                            <Text style={styles.description}>
                                Scan, process, and manage your documents with unparalleled precision and speed.
                            </Text>
                        </BlurView>
                    </Animated.View>

                    <Animated.View entering={FadeInDown.delay(600).duration(1000)} style={styles.buttonContainer}>
                        <Link href="/(auth)/login" asChild>
                            <TouchableOpacity style={styles.button}>
                                <Text style={styles.buttonText}>Get Started</Text>
                            </TouchableOpacity>
                        </Link>
                    </Animated.View>
                </View>
            </SafeAreaView>
        </View>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
    },
    background: {
        position: 'absolute',
        left: 0,
        right: 0,
        top: 0,
        bottom: 0,
    },
    safeArea: {
        flex: 1,
    },
    contentContainer: {
        flex: 1,
        padding: 24,
        justifyContent: 'space-between',
        paddingVertical: 60,
    },
    heroSection: {
        alignItems: 'center',
        marginTop: 40,
    },
    title: {
        fontSize: 56,
        fontWeight: '800',
        color: '#fff',
        letterSpacing: -1,
    },
    titleAccent: {
        fontSize: 56,
        fontWeight: '300',
        color: '#1A2595', // True Cobalt
        marginTop: -10,
        letterSpacing: 2,
    },
    cardContainer: {
        marginTop: 20,
    },
    card: {
        overflow: 'hidden',
        borderRadius: 24,
        padding: 30,
        backgroundColor: 'rgba(255,255,255,0.05)',
        borderWidth: 1,
        borderColor: 'rgba(255,255,255,0.1)',
    },
    tagline: {
        color: '#fff',
        fontSize: 20,
        fontWeight: '600',
        marginBottom: 12,
    },
    description: {
        color: '#ccc',
        fontSize: 16,
        lineHeight: 24,
    },
    buttonContainer: {
        width: '100%',
    },
    button: {
        backgroundColor: '#1A2595',
        paddingVertical: 18,
        borderRadius: 16,
        width: '100%',
        alignItems: 'center',
        shadowColor: '#1A2595',
        shadowOffset: { width: 0, height: 8 },
        shadowOpacity: 0.4,
        shadowRadius: 16,
        elevation: 8,
    },
    buttonText: {
        color: '#fff',
        fontSize: 18,
        fontWeight: '700',
        letterSpacing: 0.5,
    },
});
