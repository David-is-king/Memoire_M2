// lib/screens/alerts_screen.dart

import 'dart:async';
import 'package:flutter/material.dart';
import '../models/models.dart';
import '../services/api_service.dart';
import '../services/ws_service.dart';
import '../theme/app_theme.dart';
import '../widgets/shared_widgets.dart';

class AlertsScreen extends StatefulWidget {
  const AlertsScreen({super.key});
  @override
  State<AlertsScreen> createState() => _AlertsScreenState();
}

class _AlertsScreenState extends State<AlertsScreen> with SingleTickerProviderStateMixin {
  final _api = ApiService();
  final _ws  = WsService();

  List<AlertItem> _alerts = [];
  bool _loading = true;
  bool _showHistory = false;
  late StreamSubscription _alertSub;
  late TabController _tab;

  @override
  void initState() {
    super.initState();
    _tab = TabController(length: 2, vsync: this);
    _tab.addListener(() => setState(() => _showHistory = _tab.index == 1));
    _load();
    _ws.connect();
    _alertSub = _ws.onAlert.listen((a) {
      if (mounted) setState(() => _alerts.insert(0, a));
    });
  }

  Future<void> _load() async {
    try {
      final a = await _api.getAlerts();
      if (mounted) setState(() { _alerts = a; _loading = false; });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _markAll() async {
    await _api.markAllRead();
    setState(() => _alerts = _alerts.map((a) => a.copyWith(isRead: true)).toList());
  }

  List<AlertItem> get _active  => _alerts.where((a) => !a.isRead).toList();
  List<AlertItem> get _history => _alerts.where((a) => a.isRead).toList();

  @override
  void dispose() {
    _alertSub.cancel(); _ws.dispose(); _api.dispose(); _tab.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: AppBar(
        title: const Text('Alerts', style: AppText.h2),
        actions: [
          IconButton(icon: const Icon(Icons.search_rounded, color: AppColors.textMid), onPressed: () {}),
        ],
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(52),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 10),
            child: _TabToggle(
              labels: const ['Active', 'History'],
              controller: _tab,
            ),
          ),
        ),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: AppColors.primary))
          : TabBarView(
              controller: _tab,
              children: [
                _AlertList(
                  alerts: _active,
                  emptyMsg: 'No active alerts 🎉',
                  onMarkRead: (id) async {
                    await _api.markRead(id);
                    setState(() {
                      final i = _alerts.indexWhere((a) => a.id == id);
                      if (i != -1) _alerts[i] = _alerts[i].copyWith(isRead: true);
                    });
                  },
                ),
                _AlertList(alerts: _history, emptyMsg: 'No history yet'),
              ],
            ),
      bottomNavigationBar: _active.isNotEmpty
          ? Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
              child: PrimaryButton(
                label: 'View All Alerts',
                icon: Icons.arrow_forward_rounded,
                onTap: _markAll,
              ),
            )
          : null,
    );
  }
}

// ── Tab Toggle (Active / History pill) ───────────────────
class _TabToggle extends StatelessWidget {
  final List<String> labels;
  final TabController controller;
  const _TabToggle({required this.labels, required this.controller});

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (_, __) => Container(
        padding: const EdgeInsets.all(4),
        decoration: BoxDecoration(
          color: AppColors.border, borderRadius: BorderRadius.circular(14),
        ),
        child: Row(
          children: List.generate(labels.length, (i) {
            final sel = controller.index == i;
            return Expanded(child: GestureDetector(
              onTap: () => controller.animateTo(i),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                padding: const EdgeInsets.symmetric(vertical: 9),
                decoration: BoxDecoration(
                  color: sel ? AppColors.primary : Colors.transparent,
                  borderRadius: BorderRadius.circular(10),
                  boxShadow: sel ? blueShadow() : [],
                ),
                child: Text(labels[i],
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontFamily: 'Nunito', fontSize: 13, fontWeight: FontWeight.w700,
                    color: sel ? Colors.white : AppColors.textMid,
                  ),
                ),
              ),
            ));
          }),
        ),
      ),
    );
  }
}

// ── Alert List ────────────────────────────────────────────
class _AlertList extends StatelessWidget {
  final List<AlertItem> alerts;
  final String emptyMsg;
  final Future<void> Function(String)? onMarkRead;

  const _AlertList({required this.alerts, required this.emptyMsg, this.onMarkRead});

  @override
  Widget build(BuildContext context) {
    if (alerts.isEmpty) {
      return Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
        const Text('🔔', style: TextStyle(fontSize: 40)),
        const SizedBox(height: 12),
        Text(emptyMsg, style: AppText.body),
      ]));
    }
    return ListView.separated(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 100),
      itemCount: alerts.length,
      separatorBuilder: (_, __) => const SizedBox(height: 10),
      itemBuilder: (_, i) => _AlertTile(alert: alerts[i], onMarkRead: onMarkRead),
    );
  }
}

// ── Alert Tile ────────────────────────────────────────────
class _AlertTile extends StatelessWidget {
  final AlertItem alert;
  final Future<void> Function(String)? onMarkRead;
  const _AlertTile({required this.alert, this.onMarkRead});

  ({Color fg, Color bg, IconData icon}) get _cfg => switch (alert.severity) {
    AlertSeverity.critical => (fg: AppColors.critical, bg: AppColors.criticalBg, icon: Icons.local_fire_department_rounded),
    AlertSeverity.warning  => (fg: AppColors.warning,  bg: AppColors.warningBg,  icon: Icons.warning_amber_rounded),
    AlertSeverity.info     => (fg: AppColors.info,     bg: AppColors.infoBg,     icon: Icons.info_outline_rounded),
    AlertSeverity.ok       => (fg: AppColors.healthy,  bg: AppColors.healthyBg,  icon: Icons.check_circle_outline_rounded),
  };

  String _relative(DateTime dt) {
    final diff = DateTime.now().difference(dt);
    if (diff.inMinutes < 60) return '${diff.inMinutes} min ago';
    if (diff.inHours < 24)   return '${diff.inHours} hours ago';
    return '${diff.inDays} days ago';
  }

  @override
  Widget build(BuildContext context) {
    final c = _cfg;
    return GestureDetector(
      onTap: onMarkRead != null ? () => onMarkRead!(alert.id) : null,
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(16),
          boxShadow: cardShadow(),
          border: Border.all(
            color: alert.isRead ? Colors.transparent : c.fg.withOpacity(0.15),
          ),
        ),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Container(
            width: 40, height: 40,
            decoration: BoxDecoration(color: c.bg, borderRadius: BorderRadius.circular(12)),
            child: Icon(c.icon, color: c.fg, size: 20),
          ),
          const SizedBox(width: 12),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Expanded(child: Text(alert.deviceName, style: AppText.h3)),
              AlertBadge(severity: alert.severity),
            ]),
            const SizedBox(height: 3),
            Text(alert.title, style: AppText.body.copyWith(
              color: AppColors.textDark, fontWeight: FontWeight.w600)),
            const SizedBox(height: 2),
            Text(_relative(alert.createdAt), style: AppText.sm),
          ])),
        ]),
      ),
    );
  }
}