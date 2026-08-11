if (typeof globalThis.setImmediate !== 'function') {
  Object.defineProperty(globalThis, 'setImmediate', {
    configurable: true,
    value: (callback: unknown, ...args: unknown[]) => {
      if (typeof callback !== 'function') throw new TypeError('setImmediate callback must be a function')
      return setTimeout(() => callback(...args), 0)
    },
  })
}
