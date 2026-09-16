import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { theme } from '../src/theme';

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <StatusBar style="light" />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: theme.elevated },
          headerTintColor: theme.fg,
          headerTitleStyle: { fontSize: 16, fontWeight: '600' },
          headerShadowVisible: false,
          contentStyle: { backgroundColor: theme.bg },
          animation: 'slide_from_right',
        }}
      >
        <Stack.Screen name="index" options={{ title: 'CodePilot Remote' }} />
        <Stack.Screen name="pair" options={{ title: 'Pair with your PC' }} />
        <Stack.Screen name="projects" options={{ title: 'Projects' }} />
        <Stack.Screen name="project/[id]" options={{ title: 'Project' }} />
        <Stack.Screen name="new-task" options={{ title: 'New Task' }} />
        <Stack.Screen name="session/[id]" options={{ title: 'Session' }} />
        <Stack.Screen name="diff" options={{ title: 'Diff' }} />
        <Stack.Screen name="connection" options={{ title: 'Connection' }} />
      </Stack>
    </SafeAreaProvider>
  );
}
