import React, { useState, useEffect, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Dimensions,
  TouchableOpacity,
  Animated,
  Modal,
} from 'react-native';
import { X, ChevronRight } from 'lucide-react-native';

const { width, height } = Dimensions.get('window');

// Theme colors
const colors = {
  inkBlack: '#070712',
  mayaBlue: '#89C7FE',
  trueCobalt: '#1A2595',
  shadowGrey: '#191B26',
  white: '#FCFEFF',
};

interface TutorialStep {
  id: string;
  title: string;
  description: string;
  targetArea?: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
  position?: 'top' | 'bottom' | 'center';
}

interface TutorialOverlayProps {
  visible: boolean;
  onComplete: () => void;
  steps: TutorialStep[];
  tutorialKey: string;
}

export function TutorialOverlay({
  visible,
  onComplete,
  steps,
  tutorialKey,
}: TutorialOverlayProps) {
  const [currentStep, setCurrentStep] = useState(0);
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const slideAnim = useRef(new Animated.Value(50)).current;

  useEffect(() => {
    if (visible) {
      setCurrentStep(0);
      Animated.parallel([
        Animated.timing(fadeAnim, {
          toValue: 1,
          duration: 300,
          useNativeDriver: true,
        }),
        Animated.timing(slideAnim, {
          toValue: 0,
          duration: 300,
          useNativeDriver: true,
        }),
      ]).start();
    }
  }, [visible]);

  const handleNext = () => {
    if (currentStep < steps.length - 1) {
      // Animate to next step
      Animated.sequence([
        Animated.parallel([
          Animated.timing(fadeAnim, {
            toValue: 0,
            duration: 150,
            useNativeDriver: true,
          }),
          Animated.timing(slideAnim, {
            toValue: -20,
            duration: 150,
            useNativeDriver: true,
          }),
        ]),
        Animated.parallel([
          Animated.timing(fadeAnim, {
            toValue: 1,
            duration: 200,
            useNativeDriver: true,
          }),
          Animated.timing(slideAnim, {
            toValue: 0,
            duration: 200,
            useNativeDriver: true,
          }),
        ]),
      ]).start();
      
      setCurrentStep(currentStep + 1);
    } else {
      handleComplete();
    }
  };

  const handleComplete = () => {
    Animated.timing(fadeAnim, {
      toValue: 0,
      duration: 200,
      useNativeDriver: true,
    }).start(() => {
      onComplete();
    });
  };

  const handleSkip = () => {
    handleComplete();
  };

  if (!visible || steps.length === 0) {
    return null;
  }

  const step = steps[currentStep];
  const isLastStep = currentStep === steps.length - 1;

  return (
    <Modal
      visible={visible}
      transparent
      animationType="none"
      statusBarTranslucent
    >
      <View style={styles.overlay}>
        {/* Skip button */}
        <TouchableOpacity
          style={styles.skipButton}
          onPress={handleSkip}
          hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
        >
          <X size={24} color={colors.white} />
        </TouchableOpacity>

        {/* Spotlight cutout (if target area specified) */}
        {step.targetArea && (
          <View
            style={[
              styles.spotlight,
              {
                left: step.targetArea.x,
                top: step.targetArea.y,
                width: step.targetArea.width,
                height: step.targetArea.height,
              },
            ]}
          />
        )}

        {/* Content card */}
        <Animated.View
          style={[
            styles.contentCard,
            step.position === 'top' && styles.contentTop,
            step.position === 'bottom' && styles.contentBottom,
            step.position === 'center' && styles.contentCenter,
            {
              opacity: fadeAnim,
              transform: [{ translateY: slideAnim }],
            },
          ]}
        >
          {/* Step indicator */}
          <View style={styles.stepIndicator}>
            {steps.map((_, index) => (
              <View
                key={index}
                style={[
                  styles.stepDot,
                  index === currentStep && styles.stepDotActive,
                  index < currentStep && styles.stepDotCompleted,
                ]}
              />
            ))}
          </View>

          <Text style={styles.title}>{step.title}</Text>
          <Text style={styles.description}>{step.description}</Text>

          {/* Action buttons */}
          <View style={styles.actions}>
            {!isLastStep && (
              <TouchableOpacity onPress={handleSkip}>
                <Text style={styles.skipText}>Skip Tutorial</Text>
              </TouchableOpacity>
            )}
            
            <TouchableOpacity
              style={styles.nextButton}
              onPress={handleNext}
              activeOpacity={0.8}
            >
              <Text style={styles.nextText}>
                {isLastStep ? 'Got it!' : 'Next'}
              </Text>
              {!isLastStep && <ChevronRight size={18} color={colors.white} />}
            </TouchableOpacity>
          </View>
        </Animated.View>
      </View>
    </Modal>
  );
}

// Pre-defined tutorial steps for different screens
export const vaultTutorialSteps: TutorialStep[] = [
  {
    id: 'vault-intro',
    title: 'Your Document Vault',
    description: 'All your master documents are stored here securely. Tap any document to view details or adapt it for portals.',
    position: 'center',
  },
  {
    id: 'vault-add',
    title: 'Add New Documents',
    description: 'Tap the + button to capture a new photo or signature using your camera.',
    position: 'bottom',
  },
  {
    id: 'vault-actions',
    title: 'Quick Actions',
    description: 'Long press any document for quick actions like delete, share, or rename.',
    position: 'center',
  },
];

export const cameraTutorialSteps: TutorialStep[] = [
  {
    id: 'camera-frame',
    title: 'Frame Your Document',
    description: 'Position your document within the frame. We\'ll automatically detect edges and enhance quality.',
    position: 'top',
  },
  {
    id: 'camera-lighting',
    title: 'Good Lighting',
    description: 'Ensure your document is well-lit with no shadows for best results.',
    position: 'center',
  },
  {
    id: 'camera-capture',
    title: 'Capture',
    description: 'Tap the capture button when ready. Hold steady for the sharpest image.',
    position: 'bottom',
  },
];

export const adaptTutorialSteps: TutorialStep[] = [
  {
    id: 'adapt-select',
    title: 'Select Target Portal',
    description: 'Choose which exam or application portal you need to submit to.',
    position: 'top',
  },
  {
    id: 'adapt-auto',
    title: 'Automatic Formatting',
    description: 'We\'ll resize, compress, and format your document to meet exact requirements.',
    position: 'center',
  },
  {
    id: 'adapt-download',
    title: 'Download & Submit',
    description: 'Once ready, download the adapted file directly to your device.',
    position: 'bottom',
  },
];

// Hook to manage tutorial state
export function useTutorial(tutorialKey: string) {
  const [showTutorial, setShowTutorial] = useState(false);
  const [hasSeenTutorial, setHasSeenTutorial] = useState(true); // Default to seen

  useEffect(() => {
    // Check if user has seen this tutorial (would use AsyncStorage in real app)
    const checkTutorialStatus = async () => {
      try {
        // const seen = await AsyncStorage.getItem(`tutorial_${tutorialKey}`);
        // setHasSeenTutorial(seen === 'true');
        // For now, show tutorial for first-time users
        setHasSeenTutorial(true);
      } catch (error) {
        setHasSeenTutorial(true);
      }
    };

    checkTutorialStatus();
  }, [tutorialKey]);

  const startTutorial = () => {
    setShowTutorial(true);
  };

  const completeTutorial = async () => {
    setShowTutorial(false);
    setHasSeenTutorial(true);
    try {
      // await AsyncStorage.setItem(`tutorial_${tutorialKey}`, 'true');
    } catch (error) {
      // Ignore storage errors
    }
  };

  return {
    showTutorial,
    hasSeenTutorial,
    startTutorial,
    completeTutorial,
  };
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.85)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  skipButton: {
    position: 'absolute',
    top: 60,
    right: 20,
    zIndex: 10,
    padding: 8,
  },
  spotlight: {
    position: 'absolute',
    borderRadius: 8,
    borderWidth: 2,
    borderColor: colors.mayaBlue,
    backgroundColor: 'transparent',
    // Creates spotlight effect with box shadow
    shadowColor: colors.mayaBlue,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.5,
    shadowRadius: 20,
    elevation: 10,
  },
  contentCard: {
    backgroundColor: colors.shadowGrey,
    borderRadius: 16,
    padding: 24,
    marginHorizontal: 24,
    maxWidth: 340,
    borderWidth: 1,
    borderColor: colors.mayaBlue + '30',
  },
  contentTop: {
    position: 'absolute',
    top: 120,
  },
  contentBottom: {
    position: 'absolute',
    bottom: 120,
  },
  contentCenter: {
    // Default centered position
  },
  stepIndicator: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 8,
    marginBottom: 20,
  },
  stepDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.white + '30',
  },
  stepDotActive: {
    backgroundColor: colors.mayaBlue,
    width: 24,
  },
  stepDotCompleted: {
    backgroundColor: colors.mayaBlue + '60',
  },
  title: {
    fontSize: 20,
    fontWeight: 'bold',
    color: colors.white,
    textAlign: 'center',
    marginBottom: 12,
  },
  description: {
    fontSize: 15,
    color: colors.white + 'CC',
    textAlign: 'center',
    lineHeight: 22,
    marginBottom: 24,
  },
  actions: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  skipText: {
    color: colors.mayaBlue,
    fontSize: 14,
  },
  nextButton: {
    backgroundColor: colors.trueCobalt,
    paddingVertical: 12,
    paddingHorizontal: 24,
    borderRadius: 8,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginLeft: 'auto',
  },
  nextText: {
    color: colors.white,
    fontSize: 16,
    fontWeight: '600',
  },
});
