// ─────────────────────────────────────────────
// screens/intervention_detail_screen.dart
// Ecran 7 : Détail intervention
// Ecran 8 : Intervention en cours (même écran, état différent)
// ─────────────────────────────────────────────

import 'package:flutter/material.dart';
import 'sensor_data.dart';
import 'api_service.dart';
import 'app_theme.dart';
import 'status_badge.dart';

class InterventionDetailScreen extends StatefulWidget {
  final InterventionModel intervention;
  const InterventionDetailScreen({super.key, required this.intervention});

  @override
  State<InterventionDetailScreen> createState() => _InterventionDetailScreenState();
}

class _InterventionDetailScreenState extends State<InterventionDetailScreen> {
  final _api = ApiService();
  late InterventionModel _item;
  final _noteController = TextEditingController();
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _item = widget.intervention;
  }

  @override
  void dispose() {
    _noteController.dispose();
    super.dispose();
  }

  Future<void> _startIntervention() async {
    setState(() => _saving = true);
    try {
      await _api.updateInterventionStatus(_item.id, InterventionStatus.inProgress);
      setState(() {
        _item = _item.copyWith(status: InterventionStatus.inProgress, progress: 0.0);
      });
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Impossible de démarrer l\'intervention')),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _finishIntervention() async {
    setState(() => _saving = true);
    try {
      await _api.updateInterventionStatus(_item.id, InterventionStatus.done);
      setState(() {
        _item = _item.copyWith(status: InterventionStatus.done, progress: 1.0);
      });
      if (mounted) Navigator.pop(context);
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Impossible de terminer l\'intervention')),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _toggleChecklistItem(int index) async {
    final updated = [..._item.checklist];
    updated[index] = updated[index].copyWith(done: !updated[index].done);
    setState(() => _item = _item.copyWith(checklist: updated));
  }

  Future<void> _addNote() async {
    final text = _noteController.text.trim();
    if (text.isEmpty) return;
    try {
      await _api.addInterventionNote(_item.id, text);
    } catch (_) {}
    setState(() {
      _item = _item.copyWith(notes: [..._item.notes, text]);
      _noteController.clear();
    });
  }

  (Color, String) get _priorityStyle => switch (_item.priority) {
        InterventionPriority.critical => (AppTheme.danger, 'Critique'),
        InterventionPriority.major => (AppTheme.warning, 'Majeur'),
        InterventionPriority.normal => (AppTheme.primary, 'Planifié'),
        InterventionPriority.low => (AppTheme.success, 'Faible'),
      };

  bool get _isInProgress => _item.status == InterventionStatus.inProgress;

  @override
  Widget build(BuildContext context) {
    final (color, label) = _priorityStyle;

    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
          onPressed: () => Navigator.pop(context),
        ),
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(_item.motorName, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: Colors.white)),
            Text(_item.motorLocation, style: const TextStyle(fontSize: 11, color: Colors.white70)),
          ],
        ),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 12),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
              decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.15), borderRadius: BorderRadius.circular(20)),
              child: Text(label, style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w700)),
            ),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Row(
            children: [
              Expanded(child: Text(_item.type, style: AppTextStyles.headingMedium)),
            ],
          ),
          const SizedBox(height: 4),
          Text('Planifiée le ${_formatDate(_item.scheduledAt)}', style: AppTextStyles.labelMono),
          const SizedBox(height: 20),

          if (_isInProgress) ...[
            const Text('Progression', style: AppTextStyles.headingSmall),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(6),
                    child: LinearProgressIndicator(
                      value: _item.progress,
                      minHeight: 8,
                      backgroundColor: AppTheme.border,
                      valueColor: const AlwaysStoppedAnimation(AppTheme.primary),
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                Text('${(_item.progress * 100).toInt()}%', style: AppTextStyles.headingSmall),
              ],
            ),
            const SizedBox(height: 16),
            if (_item.currentStep != null) ...[
              const Text('Étape actuelle', style: AppTextStyles.headingSmall),
              const SizedBox(height: 6),
              Text(_item.currentStep!, style: AppTextStyles.bodyText),
              const SizedBox(height: 20),
            ],
          ],

          const Text('Description', style: AppTextStyles.headingSmall),
          const SizedBox(height: 8),
          Text(_item.description, style: AppTextStyles.bodyText),
          const SizedBox(height: 20),

          if (_item.checklist.isNotEmpty) ...[
            const Text('Checklist', style: AppTextStyles.headingSmall),
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.symmetric(vertical: 4),
              decoration: BoxDecoration(
                color: AppTheme.surface,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: AppTheme.border),
              ),
              child: Column(
                children: List.generate(_item.checklist.length, (i) {
                  final c = _item.checklist[i];
                  return CheckboxListTile(
                    value: c.done,
                    onChanged: _isInProgress ? (_) => _toggleChecklistItem(i) : null,
                    title: Text(c.label,
                        style: TextStyle(
                          fontSize: 13,
                          color: AppTheme.textPrimary,
                          decoration: c.done ? TextDecoration.lineThrough : null,
                        )),
                    activeColor: AppTheme.primary,
                    controlAffinity: ListTileControlAffinity.leading,
                    dense: true,
                  );
                }),
              ),
            ),
            const SizedBox(height: 20),
          ],

          if (_isInProgress) ...[
            const Text('Notes', style: AppTextStyles.headingSmall),
            const SizedBox(height: 8),
            ..._item.notes.map((n) => Container(
                  margin: const EdgeInsets.only(bottom: 6),
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(color: AppTheme.surfaceElevated, borderRadius: BorderRadius.circular(10)),
                  child: Text(n, style: AppTextStyles.bodyText),
                )),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _noteController,
                    decoration: InputDecoration(
                      hintText: 'Ajouter une note...',
                      filled: true,
                      fillColor: AppTheme.surface,
                      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: const BorderSide(color: AppTheme.border)),
                      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: const BorderSide(color: AppTheme.border)),
                    ),
                  ),
                ),
                IconButton(
                  onPressed: _addNote,
                  icon: const Icon(Icons.camera_alt_outlined, color: AppTheme.textSecondary),
                ),
              ],
            ),
            const SizedBox(height: 20),
            const Text('Photos', style: AppTextStyles.headingSmall),
            const SizedBox(height: 8),
            SizedBox(
              height: 70,
              child: ListView(
                scrollDirection: Axis.horizontal,
                children: [
                  ..._item.photoUrls.map((url) => Container(
                        margin: const EdgeInsets.only(right: 8),
                        width: 70,
                        decoration: BoxDecoration(
                          color: AppTheme.surfaceElevated,
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(color: AppTheme.border),
                        ),
                        child: const Icon(Icons.image_outlined, color: AppTheme.textMuted),
                      )),
                  Container(
                    width: 70,
                    decoration: BoxDecoration(
                      color: AppTheme.surfaceElevated,
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(color: AppTheme.border),
                    ),
                    child: const Icon(Icons.add_rounded, color: AppTheme.textMuted),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),
          ],

          SizedBox(
            width: double.infinity,
            height: 52,
            child: ElevatedButton(
              onPressed: _saving
                  ? null
                  : _isInProgress
                      ? _finishIntervention
                      : _item.status == InterventionStatus.done
                          ? null
                          : _startIntervention,
              style: ElevatedButton.styleFrom(
                backgroundColor: AppTheme.primary,
                disabledBackgroundColor: AppTheme.primary.withValues(alpha: 0.5),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
              child: _saving
                  ? const SizedBox(height: 22, width: 22, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2.5))
                  : Text(
                      _item.status == InterventionStatus.done
                          ? 'Intervention terminée'
                          : _isInProgress
                              ? 'Terminer l\'intervention'
                              : 'Démarrer l\'intervention',
                      style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600, fontSize: 15),
                    ),
            ),
          ),
        ],
      ),
    );
  }

  String _formatDate(DateTime dt) {
    return '${dt.day.toString().padLeft(2, '0')}/'
        '${dt.month.toString().padLeft(2, '0')}/'
        '${dt.year} ${dt.hour.toString().padLeft(2, '0')}:'
        '${dt.minute.toString().padLeft(2, '0')}';
  }
}
