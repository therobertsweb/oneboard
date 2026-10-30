import 'package:flutter/material.dart';
import 'board_api.dart';

/// Extract the token locally. Never navigate to a pasted URL or send session
/// credentials to its host.
String authLinkToken(String input, {required bool reset}) {
  final value = input.trim();
  final uri = Uri.tryParse(value);
  if (uri != null && uri.hasScheme) {
    final parts = uri.pathSegments;
    final expected = reset ? 'reset-password' : 'verify-email';
    if (!{'http', 'https'}.contains(uri.scheme) ||
        parts.length != 2 ||
        parts.first != expected) {
      throw const FormatException(
        'Paste the matching link from your ONEBoard email.',
      );
    }
    return parts.last;
  }
  if (!RegExp(r'^[A-Za-z0-9_-]+$').hasMatch(value)) {
    throw const FormatException('Paste your ONEBoard email link or token.');
  }
  return value;
}

class AuthLinkDialog extends StatefulWidget {
  const AuthLinkDialog({
    super.key,
    required this.api,
    required this.reset,
    this.initialLink,
  });
  final BoardApi api;
  final bool reset;
  final String? initialLink;
  @override
  State<AuthLinkDialog> createState() => _AuthLinkDialogState();
}

class _AuthLinkDialogState extends State<AuthLinkDialog> {
  late final TextEditingController link;

  @override
  void initState() {
    super.initState();
    link = TextEditingController(text: widget.initialLink ?? '');
  }
  final password = TextEditingController();
  final confirmation = TextEditingController();
  bool busy = false;
  String? error;
  @override
  void dispose() {
    link.dispose();
    password.dispose();
    confirmation.dispose();
    super.dispose();
  }

  Future<void> submit() async {
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final token = authLinkToken(link.text, reset: widget.reset);
      if (widget.reset &&
          (password.text.length < 8 || password.text != confirmation.text)) {
        throw const FormatException(
          'Passwords must match and contain at least 8 characters.',
        );
      }
      await widget.api.post(
        widget.reset ? '/api/auth/reset-password' : '/api/auth/verify-email',
        {
          'token': token,
          if (widget.reset) ...{
            'password': password.text,
            'confirm_password': confirmation.text,
          },
        },
      );
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      if (mounted) {
        setState(
          () => error = e
              .toString()
              .replaceFirst('Exception: ', '')
              .replaceFirst('FormatException: ', ''),
        );
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: !busy,
    child: AlertDialog(
      title: Text(widget.reset ? 'Reset password' : 'Verify email'),
      content: SizedBox(
        width: 420,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                'Paste the link from your ONEBoard email to finish here.',
              ),
              const SizedBox(height: 16),
              TextField(
                controller: link,
                enabled: !busy,
                decoration: const InputDecoration(
                  labelText: 'Email link or token',
                ),
              ),
              if (widget.reset) ...[
                const SizedBox(height: 12),
                TextField(
                  controller: password,
                  enabled: !busy,
                  obscureText: true,
                  decoration: const InputDecoration(labelText: 'New password'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: confirmation,
                  enabled: !busy,
                  obscureText: true,
                  decoration: const InputDecoration(
                    labelText: 'Confirm password',
                  ),
                ),
              ],
              if (error != null)
                Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: Text(
                    error!,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: busy ? null : () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: busy ? null : submit,
          child: Text(busy ? 'Please wait…' : 'Confirm'),
        ),
      ],
    ),
  );
}
