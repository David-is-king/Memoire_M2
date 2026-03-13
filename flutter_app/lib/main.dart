// lib/main.dart

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'theme/app_theme.dart';
import 'screens/home_screen.dart';
import 'screens/devices_screen.dart';
import 'screens/alerts_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
    statusBarColor: Colors.transparent,
    statusBarIconBrightness: Brightness.dark,
  ));
  runApp(const PredictiveMaintenanceApp());
}

class PredictiveMaintenanceApp extends StatelessWidget {
  const PredictiveMaintenanceApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Predictive Maintenance',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light,
      home: const MainShell(),
    );
  }
}

class MainShell extends StatefulWidget {
  const MainShell({super.key});
  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  int _idx = 0;

  static const _screens = [
    HomeScreen(),
    DevicesScreen(),
    _AnalyticsPlaceholder(),
    AlertsScreen(),
    _ProfilePlaceholder(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(index: _idx, children: _screens),
      bottomNavigationBar: Container(
        decoration: BoxDecoration(
          color: AppColors.surface,
          boxShadow: [BoxShadow(
            color: const Color(0xFF0F172A).withOpacity(0.08),
            blurRadius: 20, offset: const Offset(0, -4),
          )],
        ),
        child: SafeArea(
          child: BottomNavigationBar(
            currentIndex: _idx,
            onTap: (i) => setState(() => _idx = i),
            backgroundColor: Colors.transparent,
            elevation: 0,
            items: const [
              BottomNavigationBarItem(icon: Icon(Icons.home_rounded),      label: 'Home'),
              BottomNavigationBarItem(icon: Icon(Icons.devices_rounded),   label: 'Devices'),
              BottomNavigationBarItem(icon: Icon(Icons.bar_chart_rounded), label: 'Analytics'),
              BottomNavigationBarItem(icon: Icon(Icons.notifications_rounded), label: 'Alerts'),
              BottomNavigationBarItem(icon: Icon(Icons.person_rounded),    label: 'Profile'),
            ],
          ),
        ),
      ),
    );
  }
}

class _AnalyticsPlaceholder extends StatelessWidget {
  const _AnalyticsPlaceholder();
  @override
  Widget build(BuildContext context) => const Scaffold(
    backgroundColor: AppColors.bg,
    body: Center(child: Text('Analytics — Coming soon', style: AppText.body)),
  );
}

class _ProfilePlaceholder extends StatelessWidget {
  const _ProfilePlaceholder();
  @override
  Widget build(BuildContext context) => const Scaffold(
    backgroundColor: AppColors.bg,
    body: Center(child: Text('Profile — Coming soon', style: AppText.body)),
  );
}