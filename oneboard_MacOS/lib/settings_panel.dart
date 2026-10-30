import 'dart:typed_data';

import 'package:flutter/material.dart';

import 'apple_design.dart';
import 'board_api.dart';

/// Builds the `POST /api/settings/ai-credentials` payload including only
/// non-empty keys, so untouched providers are never wiped server-side.
Map<String, dynamic> aiCredentialsPayload(
  String currentPassword,
  Map<String, String> keys,
) {
  final payload = <String, dynamic>{'current_password': currentPassword};
  keys.forEach((field, value) {
    if (value.trim().isNotEmpty) payload[field] = value.trim();
  });
  return payload;
}

bool looksLikeEmail(String value) =>
    RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(value.trim());

Widget settingsError(String message) => Container(
  padding: const EdgeInsets.all(11),
  decoration: BoxDecoration(
    color: const Color(0xFFB33142).withValues(alpha: .08),
    borderRadius: BorderRadius.circular(10),
  ),
  child: Text(
    message,
    style: const TextStyle(color: Color(0xFFB33142), fontSize: 12),
  ),
);

Widget settingsNotice(String message) => Container(
  padding: const EdgeInsets.all(11),
  decoration: BoxDecoration(
    color: boardBlue.withValues(alpha: .08),
    borderRadius: BorderRadius.circular(10),
  ),
  child: Text(
    message,
    style: const TextStyle(color: Color(0xFF245A9C), fontSize: 12),
  ),
);

Widget configuredChip(bool configured) => Container(
  padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
  decoration: BoxDecoration(
    color: (configured ? const Color(0xFF1F9D55) : boardMuted).withValues(
      alpha: .12,
    ),
    borderRadius: BorderRadius.circular(20),
  ),
  child: Text(
    configured ? 'Configured' : 'Not set',
    style: TextStyle(
      fontSize: 11,
      fontWeight: FontWeight.w600,
      color: configured ? const Color(0xFF1F9D55) : boardMuted,
    ),
  ),
);

String _cleanError(Object error) =>
    error.toString().replaceFirst('Exception: ', '');

/// Small authenticated thumbnail for avatar/logo uploads.
class _RemoteImage extends StatefulWidget {
  const _RemoteImage({required this.api, required this.path});

  final BoardApi api;
  final String path;

  @override
  State<_RemoteImage> createState() => _RemoteImageState();
}

class _RemoteImageState extends State<_RemoteImage> {
  late final Future<Uint8List?> _thumb;

  @override
  void initState() {
    super.initState();
    _thumb = _load();
  }

  Future<Uint8List?> _load() async {
    try {
      return await widget.api.getBytes(widget.path);
    } catch (_) {
      return null;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 44,
      height: 44,
      decoration: BoxDecoration(
        color: const Color(0xFFF2F2F7),
        borderRadius: BorderRadius.circular(10),
      ),
      clipBehavior: Clip.antiAlias,
      child: FutureBuilder<Uint8List?>(
        future: _thumb,
        builder: (context, snapshot) {
          final bytes = snapshot.data;
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(
              child: SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
            );
          }
          if (bytes == null || bytes.isEmpty) {
            return const Icon(
              Icons.person_outline_rounded,
              color: boardMuted,
              size: 20,
            );
          }
          return Image.memory(
            bytes,
            fit: BoxFit.cover,
            errorBuilder: (context, _, _) => const Icon(
              Icons.person_outline_rounded,
              color: boardMuted,
              size: 20,
            ),
          );
        },
      ),
    );
  }
}

/// Full Settings screen: profile, password, Buffer key, Muse credentials
/// and model, and Google OAuth details. Keys stay hidden; empty fields
/// never wipe stored values.
class SettingsPanel extends StatelessWidget {
  const SettingsPanel({
    super.key,
    required this.api,
    required this.account,
    required this.ai,
    required this.googleConfig,
    required this.pickImage,
    required this.onChanged,
  });

  final BoardApi api;
  final Map<String, dynamic> account;
  final Map<String, dynamic> ai;
  final Map<String, dynamic> googleConfig;
  final Future<String?> Function() pickImage;
  final Future<void> Function() onChanged;

  @override
  Widget build(BuildContext context) {
    final credentials =
        (ai['credentials'] as Map?)?.cast<String, dynamic>() ?? {};
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        BoardSurface(
          child: _ProfileCard(
            api: api,
            account: account,
            pickImage: pickImage,
            onChanged: onChanged,
          ),
        ),
        const SizedBox(height: 16),
        BoardSurface(child: _PasswordCard(api: api, onChanged: onChanged)),
        const SizedBox(height: 16),
        BoardSurface(
          child: _BufferCard(
            api: api,
            configured: account['buffer_api_key_configured'] == true,
            onChanged: onChanged,
          ),
        ),
        const SizedBox(height: 16),
        BoardSurface(
          child: _AiCredentialsCard(
            api: api,
            credentials: credentials,
            account: account,
            onChanged: onChanged,
          ),
        ),
        const SizedBox(height: 16),
        BoardSurface(
          child: _AiPolicyCard(api: api, ai: ai, account: account, onChanged: onChanged),
        ),
        const SizedBox(height: 16),
        BoardSurface(child: _GoogleCard(googleConfig: googleConfig)),
      ],
    );
  }
}

class _ProfileCard extends StatefulWidget {
  const _ProfileCard({
    required this.api,
    required this.account,
    required this.pickImage,
    required this.onChanged,
  });

  final BoardApi api;
  final Map<String, dynamic> account;
  final Future<String?> Function() pickImage;
  final Future<void> Function() onChanged;

  @override
  State<_ProfileCard> createState() => _ProfileCardState();
}

class _ProfileCardState extends State<_ProfileCard> {
  late final TextEditingController _name;
  late final TextEditingController _email;
  late final TextEditingController _companyName;
  late final TextEditingController _companyEmail;
  late final TextEditingController _companyWebsite;
  late final TextEditingController _currentPassword;
  bool _busy = false;
  String? _error;
  String? _notice;

  @override
  void initState() {
    super.initState();
    _name = TextEditingController();
    _email = TextEditingController();
    _companyName = TextEditingController();
    _companyEmail = TextEditingController();
    _companyWebsite = TextEditingController();
    _currentPassword = TextEditingController();
    _refill(widget.account);
  }

  @override
  void didUpdateWidget(covariant _ProfileCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.account, widget.account)) {
      _refill(widget.account);
    }
  }

  void _refill(Map<String, dynamic> account) {
    _name.text = account['name']?.toString() ?? '';
    _email.text = account['email']?.toString() ?? '';
    _companyName.text = account['company_name']?.toString() ?? '';
    _companyEmail.text = account['company_email']?.toString() ?? '';
    _companyWebsite.text = account['company_website']?.toString() ?? '';
  }

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    _companyName.dispose();
    _companyEmail.dispose();
    _companyWebsite.dispose();
    _currentPassword.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final name = _name.text.trim();
    final email = _email.text.trim().toLowerCase();
    if (name.isEmpty) {
      setState(() => _error = 'Enter your name.');
      return;
    }
    if (!looksLikeEmail(email)) {
      setState(() => _error = 'Enter a valid email address.');
      return;
    }
    final emailChanged = email != widget.account['email']?.toString();
    if (emailChanged && _currentPassword.text.isEmpty) {
      setState(
        () => _error = 'Enter your current password to change your email.',
      );
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
      _notice = null;
    });
    try {
      final result = await widget.api.post('/api/settings/account', {
        'name': name,
        'email': email,
        'company_name': _companyName.text.trim(),
        'company_email': _companyEmail.text.trim(),
        'company_website': _companyWebsite.text.trim(),
        if (emailChanged) 'current_password': _currentPassword.text,
      });
      await widget.onChanged();
      if (!mounted) return;
      final updated =
          (result['account'] as Map?)?.cast<String, dynamic>() ?? {};
      final pending = updated['pending_email']?.toString() ?? '';
      setState(() {
        _currentPassword.clear();
        _notice = pending.isNotEmpty
            ? 'Verification email sent to $pending. Keep ONEBoard open while you open the link.'
            : 'Profile saved.';
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = _cleanError(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _uploadImage(String field, String label) async {
    final path = await widget.pickImage();
    if (path == null || !mounted) return;
    setState(() {
      _busy = true;
      _error = null;
      _notice = null;
    });
    try {
      await widget.api.upload('/api/settings/account', field, path);
      await widget.onChanged();
      if (!mounted) return;
      setState(() => _notice = '$label updated.');
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = _cleanError(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _resendVerification() async {
    setState(() {
      _busy = true;
      _error = null;
      _notice = null;
    });
    try {
      await widget.api.post('/api/auth/resend-verification', {
        'email': _email.text.trim(),
      });
      if (!mounted) return;
      setState(
        () => _notice =
            'If the account is pending verification, you will receive another email.',
      );
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = _cleanError(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  String _fileLabel(String? path) {
    if (path == null || path.isEmpty) return 'No image';
    final parts = path.split('/');
    return parts.isEmpty ? path : parts.last;
  }

  @override
  Widget build(BuildContext context) {
    final verified = widget.account['email_verified'] != false;
    final pending = widget.account['pending_email']?.toString() ?? '';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Expanded(
              child: Text(
                'Profile & company',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: boardInk,
                ),
              ),
            ),
            configuredChip(verified),
          ],
        ),
        if (!verified || pending.isNotEmpty) ...[
          const SizedBox(height: 8),
          Text(
            pending.isNotEmpty
                ? 'Pending verification for $pending.'
                : 'Your email address is not verified.',
            style: const TextStyle(color: boardMuted, fontSize: 12),
          ),
          const SizedBox(height: 6),
          OutlinedButton(
            onPressed: _busy ? null : _resendVerification,
            child: const Text('Resend verification email'),
          ),
        ],
        const SizedBox(height: 12),
        TextField(
          controller: _name,
          decoration: const InputDecoration(labelText: 'Name'),
        ),
        const SizedBox(height: 11),
        TextField(
          controller: _email,
          keyboardType: TextInputType.emailAddress,
          decoration: const InputDecoration(labelText: 'Email'),
        ),
        const SizedBox(height: 11),
        TextField(
          controller: _companyName,
          decoration: const InputDecoration(labelText: 'Company'),
        ),
        const SizedBox(height: 11),
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: _companyEmail,
                keyboardType: TextInputType.emailAddress,
                decoration: const InputDecoration(
                  labelText: 'Company email',
                ),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: TextField(
                controller: _companyWebsite,
                decoration: const InputDecoration(
                  labelText: 'Company website',
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 11),
        TextField(
          controller: _currentPassword,
          obscureText: true,
          enableSuggestions: false,
          autocorrect: false,
          decoration: const InputDecoration(
            labelText: 'Current password',
            helperText: 'Required only when changing your email.',
            helperMaxLines: 2,
          ),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            if ((widget.account['avatar_path']?.toString() ?? '').isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(right: 10),
                child: _RemoteImage(
                  api: widget.api,
                  path:
                      '/uploads/avatars/${Uri.encodeComponent(_fileLabel(widget.account['avatar_path']?.toString()))}',
                ),
              ),
            Expanded(
              child: Text(
                'Avatar: ${_fileLabel(widget.account['avatar_path']?.toString())}',
                style: const TextStyle(color: boardMuted, fontSize: 12),
                overflow: TextOverflow.ellipsis,
              ),
            ),
            const SizedBox(width: 8),
            OutlinedButton(
              onPressed: _busy ? null : () => _uploadImage('avatar', 'Avatar'),
              child: const Text('Choose avatar'),
            ),
          ],
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            if ((widget.account['company_logo_path']?.toString() ?? '')
                .isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(right: 10),
                child: _RemoteImage(
                  api: widget.api,
                  path:
                      '/uploads/company-logos/${Uri.encodeComponent(_fileLabel(widget.account['company_logo_path']?.toString()))}',
                ),
              ),
            Expanded(
              child: Text(
                'Logo: ${_fileLabel(widget.account['company_logo_path']?.toString())}',
                style: const TextStyle(color: boardMuted, fontSize: 12),
                overflow: TextOverflow.ellipsis,
              ),
            ),
            const SizedBox(width: 8),
            OutlinedButton(
              onPressed: _busy
                  ? null
                  : () => _uploadImage('company_logo', 'Company logo'),
              child: const Text('Choose logo'),
            ),
          ],
        ),
        if (_error != null) ...[
          const SizedBox(height: 12),
          settingsError(_error!),
        ],
        if (_notice != null) ...[
          const SizedBox(height: 12),
          settingsNotice(_notice!),
        ],
        const SizedBox(height: 14),
        FilledButton(
          onPressed: _busy ? null : _save,
          child: const Text('Save profile'),
        ),
      ],
    );
  }
}

class _PasswordCard extends StatefulWidget {
  const _PasswordCard({required this.api, required this.onChanged});

  final BoardApi api;
  final Future<void> Function() onChanged;

  @override
  State<_PasswordCard> createState() => _PasswordCardState();
}

class _PasswordCardState extends State<_PasswordCard> {
  final _current = TextEditingController();
  final _next = TextEditingController();
  final _confirm = TextEditingController();
  bool _busy = false;
  String? _error;
  String? _notice;

  @override
  void dispose() {
    _current.dispose();
    _next.dispose();
    _confirm.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_next.text.length < 8 || _next.text != _confirm.text) {
      setState(
        () => _error =
            'The new password needs at least 8 characters and must match its confirmation.',
      );
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
      _notice = null;
    });
    try {
      await widget.api.post('/api/settings/account', {
        'current_password': _current.text,
        'new_password': _next.text,
        'confirm_password': _confirm.text,
      });
      await widget.onChanged();
      if (!mounted) return;
      setState(() {
        _current.clear();
        _next.clear();
        _confirm.clear();
        _notice = 'Password updated.';
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = _cleanError(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      const Text(
        'Password',
        style: TextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w700,
          color: boardInk,
        ),
      ),
      const SizedBox(height: 12),
      TextField(
        controller: _current,
        obscureText: true,
        enableSuggestions: false,
        autocorrect: false,
        decoration: const InputDecoration(labelText: 'Current password'),
      ),
      const SizedBox(height: 11),
      Row(
        children: [
          Expanded(
            child: TextField(
              controller: _next,
              obscureText: true,
              enableSuggestions: false,
              autocorrect: false,
              decoration: const InputDecoration(labelText: 'New password'),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: TextField(
              controller: _confirm,
              obscureText: true,
              enableSuggestions: false,
              autocorrect: false,
              decoration: const InputDecoration(labelText: 'Confirm password'),
            ),
          ),
        ],
      ),
      if (_error != null) ...[
        const SizedBox(height: 12),
        settingsError(_error!),
      ],
      if (_notice != null) ...[
        const SizedBox(height: 12),
        settingsNotice(_notice!),
      ],
      const SizedBox(height: 14),
      FilledButton(
        onPressed: _busy ? null : _save,
        child: const Text('Update password'),
      ),
    ],
  );
}

class _BufferCard extends StatefulWidget {
  const _BufferCard({
    required this.api,
    required this.configured,
    required this.onChanged,
  });

  final BoardApi api;
  final bool configured;
  final Future<void> Function() onChanged;

  @override
  State<_BufferCard> createState() => _BufferCardState();
}

class _BufferCardState extends State<_BufferCard> {
  final _key = TextEditingController();
  bool _busy = false;
  String? _error;
  String? _notice;

  @override
  void dispose() {
    _key.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    setState(() {
      _busy = true;
      _error = null;
      _notice = null;
    });
    try {
      await widget.api.post('/api/settings/account', {
        'buffer_api_key': _key.text.trim(),
      });
      await widget.onChanged();
      if (!mounted) return;
      setState(() {
        _key.clear();
        _notice = 'Buffer key saved.';
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = _cleanError(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Row(
        children: [
          const Expanded(
            child: Text(
              'Buffer',
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w700,
                color: boardInk,
              ),
            ),
          ),
          configuredChip(widget.configured),
        ],
      ),
      const SizedBox(height: 6),
      const Text(
        'Enter your Buffer API key to load channels and publish posts. Leave empty to keep the stored key.',
        style: TextStyle(color: boardMuted, fontSize: 13),
      ),
      const SizedBox(height: 12),
      TextField(
        controller: _key,
        obscureText: true,
        enableSuggestions: false,
        autocorrect: false,
        decoration: const InputDecoration(labelText: 'Buffer API key'),
      ),
      if (_error != null) ...[
        const SizedBox(height: 12),
        settingsError(_error!),
      ],
      if (_notice != null) ...[
        const SizedBox(height: 12),
        settingsNotice(_notice!),
      ],
      const SizedBox(height: 14),
      FilledButton(
        onPressed: _busy ? null : _save,
        child: const Text('Save Buffer key'),
      ),
    ],
  );
}

const _aiKeyFields = <String, String>{'muse_api_key': 'Muse'};

class _AiCredentialsCard extends StatefulWidget {
  const _AiCredentialsCard({
    required this.api,
    required this.credentials,
    required this.account,
    required this.onChanged,
  });

  final BoardApi api;
  final Map<String, dynamic> credentials;
  final Map<String, dynamic> account;
  final Future<void> Function() onChanged;

  @override
  State<_AiCredentialsCard> createState() => _AiCredentialsCardState();
}

class _AiCredentialsCardState extends State<_AiCredentialsCard> {
  final _currentPassword = TextEditingController();
  final _keys = <String, TextEditingController>{};
  bool _busy = false;
  String? _error;
  String? _notice;

  @override
  void initState() {
    super.initState();
    for (final field in _aiKeyFields.keys) {
      _keys[field] = TextEditingController();
    }
  }

  @override
  void dispose() {
    _currentPassword.dispose();
    for (final controller in _keys.values) {
      controller.dispose();
    }
    super.dispose();
  }

  bool _configured(String field) {
    if (widget.credentials[field] is bool) {
      return widget.credentials[field] == true;
    }
    return widget.account['${field}_configured'] == true;
  }

  Future<void> _save() async {
    if (_currentPassword.text.isEmpty) {
      setState(() => _error = 'Enter your current password.');
      return;
    }
    final values = <String, String>{
      for (final entry in _keys.entries) entry.key: entry.value.text,
    };
    if (values.values.every((value) => value.trim().isEmpty)) {
      setState(() => _error = 'Enter at least one new key.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
      _notice = null;
    });
    try {
      await widget.api.post(
        '/api/settings/ai-credentials',
        aiCredentialsPayload(_currentPassword.text, values),
      );
      await widget.onChanged();
      if (!mounted) return;
      setState(() {
        _currentPassword.clear();
        for (final controller in _keys.values) {
          controller.clear();
        }
        _notice = 'Muse key saved.';
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = _cleanError(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      const Text(
        'Muse credentials',
        style: TextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w700,
          color: boardInk,
        ),
      ),
      const SizedBox(height: 6),
      const Text(
        'Muse is the only AI provider. The key stays hidden; leave it empty to keep the stored key.',
        style: TextStyle(color: boardMuted, fontSize: 13),
      ),
      const SizedBox(height: 12),
      for (final entry in _aiKeyFields.entries) ...[
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: _keys[entry.key],
                obscureText: true,
                enableSuggestions: false,
                autocorrect: false,
                decoration: InputDecoration(
                  labelText: '${entry.value} API key',
                ),
              ),
            ),
            const SizedBox(width: 10),
            configuredChip(_configured(entry.key)),
          ],
        ),
        const SizedBox(height: 11),
      ],
      TextField(
        controller: _currentPassword,
        obscureText: true,
        enableSuggestions: false,
        autocorrect: false,
        decoration: const InputDecoration(labelText: 'Current password'),
      ),
      if (_error != null) ...[
        const SizedBox(height: 12),
        settingsError(_error!),
      ],
      if (_notice != null) ...[
        const SizedBox(height: 12),
        settingsNotice(_notice!),
      ],
      const SizedBox(height: 14),
      FilledButton(
        onPressed: _busy ? null : _save,
        child: const Text('Save Muse key'),
      ),
    ],
  );
}

class _AiPolicyCard extends StatefulWidget {
  const _AiPolicyCard({
    required this.api,
    required this.ai,
    required this.account,
    required this.onChanged,
  });

  final BoardApi api;
  final Map<String, dynamic> ai;
  final Map<String, dynamic> account;
  final Future<void> Function() onChanged;

  @override
  State<_AiPolicyCard> createState() => _AiPolicyCardState();
}

class _AiPolicyCardState extends State<_AiPolicyCard> {
  late final TextEditingController _model;
  bool _busy = false;
  String? _error;
  String? _notice;

  @override
  void initState() {
    super.initState();
    _model = TextEditingController();
    _refill();
  }

  @override
  void didUpdateWidget(covariant _AiPolicyCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.ai, widget.ai)) _refill();
  }

  void _refill() {
    final policy = (widget.ai['policy'] as Map?)?.cast<String, dynamic>() ?? {};
    _model.text =
        policy['model']?.toString() ??
        widget.account['ai_default_model']?.toString() ??
        '';
  }

  @override
  void dispose() {
    _model.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    setState(() {
      _busy = true;
      _error = null;
      _notice = null;
    });
    try {
      await widget.api.post('/api/settings/ai-policy', {
        'provider': 'muse',
        'model': _model.text.trim(),
      });
      await widget.onChanged();
      if (!mounted) return;
      setState(() => _notice = 'Muse model saved.');
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = _cleanError(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      const Text(
        'Muse model',
        style: TextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w700,
          color: boardInk,
        ),
      ),
      const SizedBox(height: 6),
      const Text(
        'Muse is the only AI provider. Leave the model empty for the default.',
        style: TextStyle(color: boardMuted, fontSize: 13),
      ),
      const SizedBox(height: 12),
      TextField(
        controller: _model,
        decoration: const InputDecoration(
          labelText: 'Model (optional)',
        ),
      ),
      if (_error != null) ...[
        const SizedBox(height: 12),
        settingsError(_error!),
      ],
      if (_notice != null) ...[
        const SizedBox(height: 12),
        settingsNotice(_notice!),
      ],
      const SizedBox(height: 14),
      FilledButton(
        onPressed: _busy ? null : _save,
        child: const Text('Save Muse model'),
      ),
    ],
  );
}

class _GoogleCard extends StatelessWidget {
  const _GoogleCard({required this.googleConfig});

  final Map<String, dynamic> googleConfig;

  @override
  Widget build(BuildContext context) {
    final configured = googleConfig['configured'] == true;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Expanded(
              child: Text(
                'Google OAuth',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: boardInk,
                ),
              ),
            ),
            configuredChip(configured),
          ],
        ),
        const SizedBox(height: 6),
        Text(
          configured
              ? 'Google sign-in is ready. Connect from the dashboard to see Search Console data.'
              : 'Google sign-in is not available in this app.',
          style: const TextStyle(color: boardMuted, fontSize: 13),
        ),
      ],
    );
  }
}

