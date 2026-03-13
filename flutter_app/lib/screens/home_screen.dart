// lib/screens/home_screen.dart

import 'dart:async';
import 'package:flutter/material.dart';
import '../models/models.dart';
import '../services/api_service.dart';
import '../services/ws_service.dart';
import '../theme/app_theme.dart';
import '../widgets/shared_widgets.dart';
import 'device_detail_screen.dart';
import '../main.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _api = ApiService();
  final _ws  = WsService();

  List<MotorDevice> _devices = [];
  bool _loading = true;
  late StreamSubscription _statusSub;
  Timer? _refresh;

  @override
  void initState() {
    super.initState();
    _load();
    _ws.connect();
    _statusSub = _ws.onStatus.listen((map) {
      setState(() {
        _devices = _devices.map((d) {
          final s = map[d.id]; if (s == null) return d;
          return MotorDevice(id: d.id, name: d.name, location: d.location,
              status: s, healthScore: d.healthScore, failureProb: d.failureProb,
              rulDays: d.rulDays, lastReading: d.lastReading,
              lastSeen: DateTime.now(), isActive: d.isActive);
        }).toList();
      });
    });
    _refresh = Timer.periodic(const Duration(seconds: 30), (_) => _load());
  }

  Future<void> _load() async {
    try {
      final devs = await _api.getDevices();
      if (mounted) setState(() { _devices = devs; _loading = false; });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  void dispose() {
    _statusSub.cancel(); _ws.dispose();
    _api.dispose(); _refresh?.cancel();
    super.dispose();
  }

  int get _totalDevices  => _devices.length;
  int get _activeDevices => _devices.where((d) => d.isActive).length;
  int get _atRisk        => _devices.where((d) => d.status == DeviceStatus.warning || d.status == DeviceStatus.critical).length;
  int get _offline       => _devices.where((d) => d.status == DeviceStatus.offline).length;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _load,
          color: AppColors.primary,
          child: CustomScrollView(
            slivers: [
              // ─ Header ─
              SliverToBoxAdapter(child: _buildHeader()),
              // ─ Stats grid ─
              SliverToBoxAdapter(child: _buildStatsGrid()),
              // ─ Equipment Health ─
              SliverToBoxAdapter(child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 24, 20, 12),
                child: SectionHeader(
                  title: 'Equipment Health',
                  actionLabel: 'See All',
                  onAction: () {},
                ),
              )),
              if (_loading)
                const SliverFillRemaining(child: Center(
                  child: CircularProgressIndicator(color: AppColors.primary),
                ))
              else
                SliverPadding(
                  padding: const EdgeInsets.symmetric(horizontal: 20),
                  sliver: SliverList.separated(
                    itemCount: _devices.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 10),
                    itemBuilder: (_, i) => DeviceListTile(
                      device: _devices[i],
                      onTap: () => Navigator.push(context, MaterialPageRoute(
                        builder: (_) => DeviceDetailScreen(deviceId: _devices[i].id),
                      )),
                    ),
                  ),
                ),
              const SliverToBoxAdapter(child: SizedBox(height: 24)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return Container(
      margin: const EdgeInsets.all(20),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [Color(0xFF1E3A8A), Color(0xFF2563EB)],
          begin: Alignment.topLeft, end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(20),
        boxShadow: blueShadow(),
      ),
      child: Row(children: [
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Predictive', style: TextStyle(
            fontFamily: 'Nunito', fontSize: 24, fontWeight: FontWeight.w400,
            color: Colors.white70, height: 1.1,
          )),
          const Text('Maintenance', style: TextStyle(
            fontFamily: 'Nunito', fontSize: 26, fontWeight: FontWeight.w800,
            color: Colors.white, letterSpacing: -0.5, height: 1.1,
          )),
          const SizedBox(height: 12),
          const Text('Overview of Equipment', style: TextStyle(
            fontFamily: 'Nunito', fontSize: 13, color: Colors.white60,
          )),
          const SizedBox(height: 14),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.15),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              const Icon(Icons.person_outline_rounded, color: Colors.white70, size: 16),
              const SizedBox(width: 8),
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Text('Hello, Admin', style: TextStyle(fontFamily: 'Nunito', color: Colors.white, fontWeight: FontWeight.w600, fontSize: 13)),
                Row(children: [
                  Container(width: 6, height: 6,
                      decoration: const BoxDecoration(color: Color(0xFF4ADE80), shape: BoxShape.circle)),
                  const SizedBox(width: 5),
                  const Text('All systems are monitored', style: TextStyle(fontFamily: 'Nunito', color: Colors.white60, fontSize: 11)),
                ]),
              ]),
            ]),
          ),
        ])),
        Container(
          width: 48, height: 48,
          decoration: BoxDecoration(
            color: Colors.white.withOpacity(0.15), shape: BoxShape.circle,
          ),
          child: const Icon(Icons.person_rounded, color: Colors.white, size: 24),
        ),
      ]),
    );
  }

  Widget _buildStatsGrid() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20),
      child: GridView.count(
        crossAxisCount: 2, shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        crossAxisSpacing: 12, mainAxisSpacing: 12, childAspectRatio: 1.5,
        children: [
          StatCard(label: 'Total Devices', value: '$_totalDevices',
              iconBg: AppColors.primary, icon: Icons.devices_rounded),
          StatCard(label: 'Active', value: '$_activeDevices',
              iconBg: AppColors.healthy, icon: Icons.check_circle_rounded,
              valueColor: AppColors.healthy),
          StatCard(label: 'At Risk', value: '$_atRisk',
              iconBg: AppColors.warning, icon: Icons.warning_rounded,
              valueColor: AppColors.warning),
          StatCard(label: 'Offline', value: '$_offline',
              iconBg: AppColors.critical, icon: Icons.signal_wifi_off_rounded,
              valueColor: AppColors.critical),
        ],
      ),
    );
  }
}