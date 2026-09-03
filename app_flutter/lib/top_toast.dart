// ─────────────────────────────────────────────
// top_toast.dart
// Notification moderne affichee en haut de l'ecran
// (remplace les SnackBar par defaut, ancrees en bas).
// ─────────────────────────────────────────────

import 'package:flutter/material.dart';
import 'app_theme.dart';

enum ToastType { success, error, info }

/// Affiche une bannière animée en haut de l'écran pendant [duration],
/// puis la retire automatiquement (ou au tap).
void showTopToast(
  BuildContext context,
  String message, {
  ToastType type = ToastType.error,
  Duration duration = const Duration(seconds: 3),
}) {
  final overlay = Overlay.of(context);
  late OverlayEntry entry;

  entry = OverlayEntry(
    builder: (context) => _TopToast(
      message: message,
      type: type,
      duration: duration,
      onDismiss: () => entry.remove(),
    ),
  );

  overlay.insert(entry);
}

class _TopToast extends StatefulWidget {
  final String message;
  final ToastType type;
  final Duration duration;
  final VoidCallback onDismiss;

  const _TopToast({
    required this.message,
    required this.type,
    required this.duration,
    required this.onDismiss,
  });

  @override
  State<_TopToast> createState() => _TopToastState();
}

class _TopToastState extends State<_TopToast> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<Offset> _slide;
  late final Animation<double> _fade;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 280),
      reverseDuration: const Duration(milliseconds: 200),
    );
    _slide = Tween<Offset>(begin: const Offset(0, -0.3), end: Offset.zero)
        .animate(CurvedAnimation(parent: _controller, curve: Curves.easeOutCubic));
    _fade = CurvedAnimation(parent: _controller, curve: Curves.easeOut);

    _controller.forward();
    Future.delayed(widget.duration, _close);
  }

  void _close() async {
    if (!mounted) return;
    await _controller.reverse();
    widget.onDismiss();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  (Color, Color, IconData) get _style {
    switch (widget.type) {
      case ToastType.success:
        return (AppTheme.success, AppTheme.successBg, Icons.check_circle_rounded);
      case ToastType.error:
        return (AppTheme.danger, AppTheme.dangerBg, Icons.error_rounded);
      case ToastType.info:
        return (AppTheme.info, AppTheme.infoBg, Icons.info_rounded);
    }
  }

  @override
  Widget build(BuildContext context) {
    final (color, bg, icon) = _style;

    return Positioned(
      top: 0,
      left: 0,
      right: 0,
      child: SafeArea(
        child: SlideTransition(
          position: _slide,
          child: FadeTransition(
            opacity: _fade,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
              child: Material(
                color: Colors.transparent,
                child: GestureDetector(
                  onTap: _close,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                    decoration: BoxDecoration(
                      color: AppTheme.surface,
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: color.withValues(alpha: 0.25)),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withValues(alpha: 0.12),
                          blurRadius: 20,
                          offset: const Offset(0, 8),
                        ),
                      ],
                    ),
                    child: Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.all(6),
                          decoration: BoxDecoration(color: bg, shape: BoxShape.circle),
                          child: Icon(icon, color: color, size: 18),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Text(
                            widget.message,
                            style: const TextStyle(
                              color: AppTheme.textPrimary,
                              fontSize: 13.5,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                        Icon(Icons.close_rounded, color: AppTheme.textMuted, size: 16),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
