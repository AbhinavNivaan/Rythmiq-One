import { StyleSheet, Text, View, TouchableOpacity } from 'react-native';
import { Link } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import Colors from '../constants/Colors';
import Animated, { FadeInDown, FadeInUp } from 'react-native-reanimated';

export default function WelcomeScreen() {
    return (
        <View style={styles.container}>
            <SafeAreaView style={styles.safeArea} edges={['top', 'bottom']}>
                <View style={styles.contentContainer}>
                    <Animated.View entering={FadeInUp.delay(200).duration(1000)} style={styles.heroSection}>
                        <Text style={styles.title}>Rythmiq</Text>
                        <Text style={styles.titleAccent}>One</Text>
                    </Animated.View>

                    <Animated.View entering={FadeInDown.delay(400).duration(1000)} style={styles.cardContainer}>
                        <View style={styles.card}>
                            <Text style={styles.tagline}>Premium Document Intelligence</Text>
                            <Text style={styles.description}>
                                Scan, process, and manage your documents with unparalleled precision and speed.
                            </Text>
                        </View>
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
        backgroundColor: Colors.palette.inkBlack,
    },
    safeArea: {
        flex: 1,
    },
    contentContainer: {
        flex: 1,
        paddingHorizontal: 24,
        paddingTop: 24,
        paddingBottom: 20,
        justifyContent: 'space-between',
    },
    heroSection: {
        alignItems: 'flex-start',
        marginTop: 8,
    },
    title: {
        fontSize: 56,
        fontWeight: '800',
        color: Colors.palette.white,
        letterSpacing: -1,
    },
    titleAccent: {
        fontSize: 56,
        fontWeight: '600',
        color: '#999',
        marginTop: -10,
        letterSpacing: 0,
    },
    cardContainer: {
        marginTop: 16,
    },
    card: {
        borderRadius: 24,
        padding: 30,
        backgroundColor: Colors.palette.shadowGrey,
        borderWidth: 1,
        borderColor: 'rgba(255, 255, 255, 0.05)',
    },
    tagline: {
        color: Colors.palette.white,
        fontSize: 20,
        fontWeight: '700',
        marginBottom: 12,
    },
    description: {
        color: '#999',
        fontSize: 16,
        lineHeight: 24,
    },
    buttonContainer: {
        width: '100%',
    },
    button: {
        backgroundColor: '#1A2595',
        paddingVertical: 16,
        borderRadius: 12,
        width: '100%',
        alignItems: 'center',
    },
    buttonText: {
        color: Colors.palette.white,
        fontSize: 18,
        fontWeight: '600',
    },
});
