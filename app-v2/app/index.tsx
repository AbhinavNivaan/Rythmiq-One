import { useEffect, useState } from 'react';
import { Redirect } from 'expo-router';
import * as SecureStore from 'expo-secure-store';
import { useAuth } from '../contexts/AuthContext';
import { supabase } from '../services/api';

const ONBOARDING_SEEN_KEY = 'rythmiq_onboarding_seen';

export default function Index() {
  const { isLoading, isAuthenticated } = useAuth();
  const [onboardingChecked, setOnboardingChecked] = useState(false);
  const [onboardingSeen, setOnboardingSeen] = useState(false);

  useEffect(() => {
    if (isLoading) return; // wait for auth to resolve first

    (async () => {
      let seen = await SecureStore.getItemAsync(ONBOARDING_SEEN_KEY);

      // Migration for existing installs (v4/v5): if no flag but a Supabase
      // session exists in SecureStore, the user has already seen onboarding.
      if (!seen && supabase) {
        const { data } = await supabase.auth.getSession();
        if (data.session) {
          await SecureStore.setItemAsync(ONBOARDING_SEEN_KEY, 'true');
          seen = 'true';
        }
      }

      setOnboardingSeen(seen === 'true');
      setOnboardingChecked(true);
    })();
  }, [isLoading]);

  if (isLoading || !onboardingChecked) return null;

  if (isAuthenticated) return <Redirect href="/(tabs)/dashboard" />;

  if (onboardingSeen) return <Redirect href="/(auth)/login" />;

  return <Redirect href="/onboarding" />;
}
