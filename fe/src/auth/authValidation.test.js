import test from 'node:test'
import assert from 'node:assert/strict'
import {
  getSafeReturnPath,
  validatePassword,
  validatePhone,
} from './authValidation.js'

test('accepts supported Vietnamese mobile-number formats', () => {
  assert.equal(validatePhone('090 123 4567'), '')
  assert.equal(validatePhone('+84 90 123 4567'), '')
})

test('rejects incomplete and unsupported phone numbers', () => {
  assert.match(validatePhone(''), /Vui lòng/)
  assert.match(validatePhone('12345'), /chưa đúng/)
  assert.match(validatePhone('+14155552671'), /chưa đúng/)
})

test('enforces the password length contract', () => {
  assert.equal(validatePassword('password-123'), '')
  assert.match(validatePassword('short'), /ít nhất 8/)
  assert.match(validatePassword('x'.repeat(129)), /quá 128/)
})

test('only accepts safe internal post-authentication return paths', () => {
  assert.equal(getSafeReturnPath('/products?category=tv'), '/products?category=tv')
  assert.equal(getSafeReturnPath('https://attacker.example'), '/')
  assert.equal(getSafeReturnPath('//attacker.example'), '/')
  assert.equal(getSafeReturnPath('/login'), '/')
  assert.equal(getSafeReturnPath('/register?from=/'), '/')
})
