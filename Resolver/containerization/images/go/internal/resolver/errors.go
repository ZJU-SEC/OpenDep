package resolver

import "fmt"

type ErrorCode string

const (
	ErrorInvalidArgument    ErrorCode = "INVALID_ARGUMENT"
	ErrorVersionNotFound    ErrorCode = "VERSION_NOT_FOUND"
	ErrorPackageNotFound    ErrorCode = "PACKAGE_NOT_FOUND"
	ErrorDataUnavailable    ErrorCode = "DATA_SOURCE_UNAVAILABLE"
	ErrorUnsupportedReplace ErrorCode = "UNSUPPORTED_REPLACE"
	ErrorProtocol           ErrorCode = "PROTOCOL_ERROR"
)

type Error struct {
	Code      ErrorCode
	Message   string
	Retryable bool
	Err       error
}

func (e *Error) Error() string {
	if e == nil {
		return ""
	}
	if e.Err == nil {
		return fmt.Sprintf("%s: %s", e.Code, e.Message)
	}
	return fmt.Sprintf("%s: %s: %v", e.Code, e.Message, e.Err)
}

func (e *Error) Unwrap() error {
	if e == nil {
		return nil
	}
	return e.Err
}
