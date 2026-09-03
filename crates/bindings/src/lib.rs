//! Cross-language bindings. FFI is not implemented yet.
//!
//! Future Python and TypeScript bindings must be generated or wrapped here,
//! not duplicated ad hoc in application packages.

/// Workspace liveness helper used by bootstrap tests.
#[must_use]
pub fn crate_status() -> &'static str {
    "ok"
}

#[cfg(test)]
mod tests {
    use super::crate_status;

    #[test]
    fn status_is_ok() {
        assert_eq!(crate_status(), "ok");
    }
}
