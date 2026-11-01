import test from 'node:test';
import assert from 'node:assert/strict';
import { safeRedirect, afterLogin, strength, validate, isCapsLockOn, confirmMismatch, MIN_PASSWORD } from '../../frontend/js/auth-page.js';

/* Pure-function tests for the login page. The server stays authoritative; these guard the client-side
 * helpers, most importantly the open-redirect check that decides where a signed-in user is sent. */

test('safeRedirect only follows same-site absolute paths', () => {
  assert.equal(safeRedirect('/admin'), '/admin');
  assert.equal(safeRedirect('/listings?x=1'), '/listings?x=1');
  for (const bad of ['//evil.example', '/\\evil.example', 'https://evil.example', 'javascript:alert(1)', 'evil', '', null, undefined, 42]) {
    assert.equal(safeRedirect(bad), '/', `must reject ${String(bad)}`);
  }
});

test('afterLogin honours ?next= only when the server chose the default "/"', () => {
  assert.equal(afterLogin('/', '/listings'), '/listings');
  assert.equal(afterLogin('/admin', '/listings'), '/admin');
  assert.equal(afterLogin('/', '//evil.example'), '/');
  assert.equal(afterLogin('//evil.example', null), '/');
  assert.equal(afterLogin('/', null), '/');
});

test('strength scores 0..4 and never rates a short password as strong', () => {
  assert.equal(strength(''), 0);
  assert.ok(strength('short1!A') < 2);
  assert.equal(strength('Correct-Horse-9-Battery'), 4);
  for (const pw of ['a', 'abcdefghij', 'ABCdef123!xyz987']) assert.ok(strength(pw) >= 0 && strength(pw) <= 4);
});

test('validate(login) requires both fields and trims the identifier', () => {
  assert.deepEqual(validate('login', { identifier: '  ', password: '' }), { identifier: 'Username or email is required.', password: 'Password is required.' });
  assert.deepEqual(validate('login', { identifier: 'a@b.co', password: 'x' }), {});
});

test('validate(signup) checks name, email shape, minimum length and confirmation', () => {
  const ok = { name: 'Ayesha Khan', email: 'ayesha@example.com', password: 'a-long-enough-pw', confirm: 'a-long-enough-pw' };
  assert.deepEqual(validate('signup', ok), {});
  assert.ok(validate('signup', { ...ok, name: ' ' }).name);
  assert.ok(validate('signup', { ...ok, email: 'not-an-email' }).email);
  assert.ok(validate('signup', { ...ok, email: '' }).email);
  const short = 'x'.repeat(MIN_PASSWORD - 1);
  assert.ok(validate('signup', { ...ok, password: short, confirm: short }).password);
  assert.equal(validate('signup', { ...ok, confirm: 'different-password' }).confirm, 'Passwords do not match.');
});

test('validate(forgot / reset / change)', () => {
  assert.ok(validate('forgot', { email: 'nope' }).email);
  assert.deepEqual(validate('forgot', { email: 'a@b.co' }), {});
  assert.ok(validate('reset', { new_password: 'x'.repeat(MIN_PASSWORD), confirm: 'y' }).confirm);
  assert.deepEqual(validate('reset', { new_password: 'x'.repeat(MIN_PASSWORD), confirm: 'x'.repeat(MIN_PASSWORD) }), {});
  assert.ok(validate('change', { current_password: '', new_password: '' }).current_password);
  assert.ok(validate('change', { current_password: 'old', new_password: 'short' }).new_password);
});

test('isCapsLockOn feature-detects getModifierState', () => {
  assert.equal(isCapsLockOn({ getModifierState: (k) => k === 'CapsLock' }), true);
  assert.equal(isCapsLockOn({ getModifierState: () => false }), false);
  assert.equal(isCapsLockOn({}), false);
  assert.equal(isCapsLockOn(null), false);
});

test('confirmMismatch is silent until the confirmation differs', () => {
  assert.equal(confirmMismatch('secret-pass-1', ''), '');
  assert.equal(confirmMismatch('secret-pass-1', 'secret-pass-1'), '');
  assert.equal(confirmMismatch('secret-pass-1', 'secret-pass-2'), 'Passwords do not match.');
});
