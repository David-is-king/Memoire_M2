// lib/screens/devices_screen.dart

import 'package:flutter/material.dart';
import '../models/models.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/shared_widgets.dart';
import 'device_detail_screen.dart';

class DevicesScreen extends StatefulWidget {
  const DevicesScreen({super.key});
  @override
  State<DevicesScreen> createState() => _DevicesScreenState();
}

class _DevicesScreenState extends State<DevicesScreen> {
  final _api = ApiService();
  List<MotorDevice> _all = [];
  List<MotorDevice> _filtered = [];
  bool _loading = true;
  String _query = '';
  DeviceStatus? _filterStatus;

  @override
  void initState() { super.initState(); _load(); }

  Future<void> _load() async {
    try {
      final d = await _api.getDevices();
      if (mounted) setState(() { _all = d; _apply(); _loading = false; });
    } catch (_) { if (mounted) setState(() => _loading = false); }
  }

  void _apply() {
    _filtered = _all.where((d) {
      final matchQ = _query.isEmpty || d.name.toLowerCase().contains(_query.toLowerCase());
      final matchS = _filterStatus == null || d.status == _filterStatus;
      return matchQ && matchS;
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: AppBar(title: const Text('Devices', style: AppText.h2)),
      body: Column(children: [
        // Search bar
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 8),
          child: TextField(
            onChanged: (v) => setState(() { _query = v; _apply(); }),
            decoration: InputDecoration(
              hintText: 'Search devices…',
              hintStyle: AppText.sm,
              prefixIcon: const Icon(Icons.search_rounded, color: AppColors.textLight, size: 20),
              filled: true, fillColor: AppColors.surface,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(14),
                borderSide: const BorderSide(color: AppColors.border),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(14),
                borderSide: const BorderSide(color: AppColors.border),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(14),
                borderSide: const BorderSide(color: AppColors.primary, width: 1.5),
              ),
              contentPadding: const EdgeInsets.symmetric(vertical: 12),
            ),
          ),
        ),
        // Filter chips
        SizedBox(height: 44, child: ListView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: 20),
          children: [null, DeviceStatus.healthy, DeviceStatus.warning, DeviceStatus.critical, DeviceStatus.offline]
              .map((s) => _FilterChip(status: s, selected: _filterStatus == s,
                  onTap: () => setState(() { _filterStatus = _filterStatus == s ? null : s; _apply(); })))
              .toList(),
        )),
        const SizedBox(height: 8),
        // List
        Expanded(child: _loading
            ? const Center(child: CircularProgressIndicator(color: AppColors.primary))
            : _filtered.isEmpty
                ? Center(child: Text('No devices found', style: AppText.body))
                : ListView.separated(
                    padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
                    itemCount: _filtered.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 10),
                    itemBuilder: (_, i) => DeviceListTile(
                      device: _filtered[i],
                      onTap: () => Navigator.push(context, MaterialPageRoute(
                          builder: (_) => DeviceDetailScreen(deviceId: _filtered[i].id))),
                    ),
                  )),
      ]),
    );
  }
}

class _FilterChip extends StatelessWidget {
  final DeviceStatus? status;
  final bool selected;
  final VoidCallback onTap;
  const _FilterChip({required this.status, required this.selected, required this.onTap});

  ({String label, Color fg, Color bg}) get _cfg => switch (status) {
    null                   => (label: 'All',      fg: AppColors.primary,  bg: AppColors.primaryLight),
    DeviceStatus.healthy   => (label: 'Healthy',  fg: AppColors.healthy,  bg: AppColors.healthyBg),
    DeviceStatus.warning   => (label: 'Warning',  fg: AppColors.warning,  bg: AppColors.warningBg),
    DeviceStatus.critical  => (label: 'Critical', fg: AppColors.critical, bg: AppColors.criticalBg),
    DeviceStatus.offline   => (label: 'Offline',  fg: AppColors.textLight, bg: AppColors.border),
  };

  @override
  Widget build(BuildContext context) {
    final c = _cfg;
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        margin: const EdgeInsets.only(right: 8),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
        decoration: BoxDecoration(
          color: selected ? c.bg : AppColors.surface,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: selected ? c.fg.withOpacity(0.4) : AppColors.border),
          boxShadow: selected ? [] : cardShadow(),
        ),
        child: Text(c.label, style: TextStyle(
          fontFamily: 'Nunito', fontSize: 12, fontWeight: FontWeight.w700,
          color: selected ? c.fg : AppColors.textMid,
        )),
      ),
    );
  }
}