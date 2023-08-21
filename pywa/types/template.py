from __future__ import annotations

__all__ = [
    'Template',
    'NewTemplate',
    'TemplateResponse',
]

import abc
import re
from dataclasses import dataclass, field
from typing import Iterable, BinaryIO
from pywa import utils

DEFAULT = object()


def _get_examples_from_placeholders(
        string: str,
        start: str = '{',
        end: str = '}'
) -> tuple[str, tuple[str]]:
    """
    Extracts the examples from a string.

    Example:

        >>> _get_examples_from_placeholders('Hello, {john}, today is {day}')
        ('Hello, {{0}}, today is {{1}}', ('john', 'day'))
        >>> _get_examples_from_placeholders('Hello, (john), today is (day)',start='(',end=')')

    Args:
      string: The string to extract the examples from.
      start: The start of the example (default: ``'{'``).
      end: The end of the example (default: ``'}'``).

    Returns:
      A tuple of the formatted string and the examples.
    """
    examples: list[str] = []
    for example in re.finditer(r'\%s(.*?)\%s' % (start, end), string):
        examples.append(example.group(1))
    for idx, example in enumerate(examples, start=1):
        string = string.replace(f"{start}{example}{end}", "{{" + str(idx) + "}}")
    return string, tuple(examples)


@dataclass(frozen=True, slots=True)
class TemplateResponse(utils.FromDict):
    """

    Attributes:
        id: the template ID.
        status: the template status.
        category: the template category.
    """
    id: str
    status: str
    category: NewTemplate.Category


class ComponentType(utils.StrEnum):
    HEADER = 'HEADER'
    BODY = 'BODY'
    FOOTER = 'FOOTER'
    BUTTONS = 'BUTTONS'


class HeaderFormatType(utils.StrEnum):
    TEXT = 'TEXT'
    IMAGE = 'IMAGE'
    VIDEO = 'VIDEO'
    DOCUMENT = 'DOCUMENT'
    LOCATION = 'LOCATION'


class ButtonType(utils.StrEnum):
    PHONE_NUMBER = 'PHONE_NUMBER'
    URL = 'URL'
    QUICK_REPLY = 'QUICK_REPLY'
    OTP = 'OTP'


class NewTemplateComponentABC(abc.ABC):
    @property
    @abc.abstractmethod
    def type(self) -> ComponentType: ...


class NewTemplateHeaderABC(NewTemplateComponentABC, abc.ABC):
    @property
    @abc.abstractmethod
    def format(self) -> HeaderFormatType: ...


class NewButtonABC(abc.ABC):
    @property
    @abc.abstractmethod
    def type(self) -> ButtonType: ...


@dataclass(slots=True)
class NewTemplate:
    """
    Represents a new template.
    `\`Create Templates\` on developers.facebook.com
    <https://developers.facebook.com/docs/whatsapp/business-management-api/message-templates>`_.

    Attributes:
        name: Name of the template (up to 512 characters, must be unique).
        category: Category of the template.
        language: The language of the template (See `Template language and locale code
         <https://developers.facebook.com/docs/whatsapp/business-management-api/message-templates/supported-languages>`_).
        body: Body of the template.
        header: Header of the template (optional).
        footer: Footer of the template (optional).
        buttons: Buttons to send with the template (optional, ``OTPButton`` is required for AUTHENTICATION).

    Example:

        >>> from pywa.types import NewTemplate as NewTemp
        >>> NewTemp(
        ...     name='buy_new_iphone_x',
        ...     category=NewTemp.Category.MARKETING,
        ...     language='en_US',
        ...     header=NewTemp.TextHeader('The New iPhone {15} is here!'),
        ...     body=NewTemp.Body('Hello {John}! Buy now and use the code {WA_IPHONE_15} to get {15%} off!'),
        ...     footer=NewTemp.Footer('Powered by PyWa'),
        ...     buttons=[
        ...         NewTemp.UrlButton(title='Buy Now', url='https://example.com/shop/{iphone15}'),
        ...         NewTemp.PhoneNumberButton(title='Call Us', phone_number='1234567890'),
        ...         NewTemp.QuickReplyButton('Unsubscribe from marketing messages'),
        ...         NewTemp.QuickReplyButton('Unsubscribe from all messages'),
        ...     ],
        ... )

        Example for Authentication template:

        >>> from pywa.types import NewTemplate as NewTemp
        >>> NewTemp(
        ...     name='auth_with_otp',
        ...     category=NewTemp.Category.AUTHENTICATION,
        ...     language='en_US',
        ...     body=NewTemp.AuthBody(
        ...         code_expiration_minutes=5,
        ...         add_security_recommendation=True
        ...     ),
        ...     buttons=NewTemp.OTPButton(
        ...         otp_type=NewTemp.OTPButton.OtpType.ONE_TAP,
        ...         title='Copy Code',
        ...         autofill_text='Autofill',
        ...         package_name='com.example.app',
        ...         signature_hash='1234567890ABCDEF1234567890ABCDEF12345678'
        ...     )
        ... )

    Templates are limited to 10 quick reply buttons. If using quick reply buttons with other buttons, buttons must be
    organized into two groups: quick reply buttons and non-quick reply buttons. If grouped incorrectly, error will be
    raised when submitting the template.

    Examples of valid groupings:
        - ``Quick Reply``, ``Quick Reply``
        - ``Quick Reply``, ``Quick Reply``, ``URL``, ``Phone``
        - ``URL``, ``Phone``, ``Quick Reply``, ``Quick Reply``

    Examples of invalid groupings:
        - ``Quick Reply``, ``URL``, ``Quick Reply``
        - ``URL``, ``Quick Reply``, ``URL``

    When you send a template that has multiple quick reply buttons, the order in which the buttons appear in the template
    is the order in which they will appear in the delivered message
    """
    name: str
    category: Category
    language: str
    body: Body | AuthBody
    header: TextHeader | ImageHeader | VideoHeader | DocumentHeader | LocationHeader | None = None
    footer: Footer | None = None
    buttons: Iterable[PhoneNumberButton | UrlButton | QuickReplyButton] | OTPButton | None = None

    def __post_init__(self):
        if self.category == self.Category.AUTHENTICATION and not (
                isinstance(self.body, self.AuthBody) or isinstance(self.buttons, self.OTPButton)
        ):
            raise ValueError('body of AuthBody and buttons of OTPButton are required for AUTHENTICATION')

    def to_dict(
            self,
            placeholder: tuple[str, str] = None
    ) -> dict[str, str | dict[str, str | tuple[str, ...]] | tuple[dict[str, str | tuple[str, ...]], ...]]:
        if isinstance(self.buttons, self.OTPButton):
            components = (
                dict(type=ComponentType.BUTTONS.value, buttons=(self.buttons.to_dict(),)),
                dict(type=ComponentType.BODY.value,
                     add_security_recommendation=self.body.add_security_recommendation),
                dict(type=ComponentType.FOOTER.value, code_expiration_minutes=self.body.code_expiration_minutes)
                if self.body.code_expiration_minutes else None,
            )
        else:
            components = (
                self.body.to_dict(placeholder),
                self.header.to_dict(placeholder) if self.header else None,
                self.footer.to_dict() if self.footer else None,
                dict(
                    type=ComponentType.BUTTONS.value,
                    buttons=tuple(button.to_dict(placeholder) for button in self.buttons)
                ) if self.buttons else None
            )
        return dict(
            name=self.name,
            category=self.category.value,
            language=self.language,
            components=tuple(component for component in components if component is not None)
        )

    class Category(utils.StrEnum):
        """
        Template category.
    
        `\`Template Categorization\` on
        developers.facebook.com
        <https://developers.facebook.com/docs/whatsapp/business-management-api/message-templates#categories>`_
        """
        AUTHENTICATION = 'AUTHENTICATION'
        MARKETING = 'MARKETING'
        UTILITY = 'UTILITY'

    @dataclass(slots=True)
    class TextHeader(NewTemplateHeaderABC):
        """
        Represents a text header.
    
        Example:
    
            >>> from pywa.types import NewTemplate
            >>> NewTemplate.TextHeader(text='Hello, {John}!')
    
        Attributes:
            text: Text to send with the header (Up to 60 characters. Supports 1 placeholder).
        """
        type: ComponentType = field(default=ComponentType.HEADER, init=False)
        format: HeaderFormatType = field(default=HeaderFormatType.TEXT, init=False)
        text: str

        def to_dict(self, placeholder: tuple[str, str] = None) -> dict[str, str | None]:
            formatted_text, examples = _get_examples_from_placeholders(self.text, *(placeholder if placeholder else ()))
            return dict(
                type=self.type.value,
                format=self.format.value,
                text=formatted_text,
                **(dict(example=dict(header_text=examples)) if examples else {})
            )

    @dataclass(slots=True)
    class ImageHeader(NewTemplateHeaderABC):
        """
        Represents an image header.
    
        Example:
            >>> from pywa.types.template import NewTemplate
            >>> NewTemplate.ImageHeader(examples=["2:c2FtcGxl..."])
    
        Attributes:
            examples: List of image handles (Use the `Resumable Upload API
             <https://developers.facebook.com/docs/graph-api/guides/upload>`_ to upload the images)
        """
        type: ComponentType = field(default=ComponentType.HEADER, init=False)
        format: HeaderFormatType = field(default=HeaderFormatType.IMAGE, init=False)
        examples: Iterable[str]

        def to_dict(self) -> dict[str, str | dict[str, tuple[str, ...]]]:
            return dict(
                type=self.type.value,
                format=self.format.value,
                example=dict(header_handle=tuple(self.examples))
            )

    @dataclass(slots=True)
    class VideoHeader(NewTemplateHeaderABC):
        """
        Represents a video header.
    
        Example:
            >>> from pywa.types import NewTemplate
            >>> NewTemplate.VideoHeader(examples=["2:c2FtcGxl..."])
    
        Attributes:
            examples: List of video handles (Use the `Resumable Upload API
             <https://developers.facebook.com/docs/graph-api/guides/upload>`_ to upload the videos)
        """
        type: ComponentType = field(default=ComponentType.HEADER, init=False)
        format: HeaderFormatType = field(default=HeaderFormatType.VIDEO, init=False)
        examples: Iterable[str]

        def to_dict(self) -> dict[str, str | dict[str, tuple[str, ...]]]:
            return dict(
                type=self.type.value,
                format=self.format.value,
                example=dict(header_handle=tuple(self.examples))
            )

    @dataclass(slots=True)
    class DocumentHeader(NewTemplateHeaderABC):
        """
        Represents a document header.
    
        Example:
            >>> from pywa.types import NewTemplate
            >>> NewTemplate.DocumentHeader(examples=["2:c2FtcGxl..."])
    
        Attributes:
            examples: List of document handles (Use the `Resumable Upload API
             <https://developers.facebook.com/docs/graph-api/guides/upload>`_ to upload the documents)
        """
        type: ComponentType = field(default=ComponentType.HEADER, init=False)
        format: HeaderFormatType = field(default=HeaderFormatType.DOCUMENT, init=False)
        examples: Iterable[str]

        def to_dict(self) -> dict[str, str | dict[str, tuple[str, ...]]]:
            return dict(
                type=self.type.value,
                format=self.format.value,
                example=dict(header_handle=tuple(self.examples))
            )

    @dataclass(slots=True)
    class LocationHeader(NewTemplateHeaderABC):
        """
        Location headers appear as generic maps at the top of the template and are useful for order tracking, delivery
        updates, ride hailing pickup/dropoff, locating physical stores, etc. When tapped, the app user's default map app
        will open and load the specified location. Locations are specified when you send the template.
    
        - Location headers can only be used in templates categorized as ``UTILITY`` or ``MARKETING``. Real-time locations are not supported.
    
        Example:
            >>> from pywa.types import NewTemplate
            >>> NewTemplate.LocationHeader()
        """
        type: ComponentType = field(default=ComponentType.HEADER, init=False)
        format: HeaderFormatType = field(default=HeaderFormatType.LOCATION, init=False)

        def to_dict(self) -> dict[str, str]:
            return dict(
                type=self.type.value,
                format=self.format.value,
            )

    @dataclass(slots=True)
    class Body(NewTemplateComponentABC):
        """
        Represents a template body.
    
        Example:
    
            >>> from pywa.types import NewTemplate
            >>> NewTemplate.Body(
            ...     text='Shop now through {the end of August} and '
            ...         'use code {25OF} to get {25%} off of all merchandise',
            ... )
    
        Attributes:
            text: Text to send with the body (Up to 1024 characters. Supports multiple placeholders).
        """
        type: ComponentType = field(default=ComponentType.BODY, init=False)
        text: str

        def to_dict(self, placeholder: tuple[str, str] = None) -> dict[str, str | None]:
            formatted_text, examples = _get_examples_from_placeholders(self.text, *(placeholder if placeholder else ()))
            return dict(
                type=self.type.value,
                text=formatted_text,
                **(dict(example=dict(body_text=(examples,))) if examples else {})
            )

    @dataclass(slots=True)
    class AuthBody:
        """
        Represents the configuration for an authentication template.

        Example:

            >>> from pywa.types import NewTemplate
            >>> NewTemplate.AuthBody(
            ...     code_expiration_minutes=5,
            ...     add_security_recommendation=True
            ... )

        Attributes:
            code_expiration_minutes: Indicates number of minutes the password or code is valid. If omitted, the code
             expiration warning will not be displayed in the delivered message. (Minimum ``1``, maximum ``90``).
            add_security_recommendation: Set to ``True`` if you want the template to include the string, ``"For your security,
             do not share this code"``. Set to ``False`` to exclude the string. Defaults to ``False``.
        """
        code_expiration_minutes: int | None = None
        add_security_recommendation: bool = False

    @dataclass(slots=True)
    class Footer(NewTemplateComponentABC):
        """
        Represents a template footer.
    
        Example:
            >>> from pywa.types import NewTemplate
            >>> NewTemplate.Footer(text='Use the link below to log in to your account.')
    
        Attributes:
            text: Text to send with the footer (Up to 60 characters, no placeholders allowed).
        """
        type: ComponentType = field(default=ComponentType.FOOTER, init=False)
        text: str

        def to_dict(self) -> dict[str, str | None]:
            return dict(
                type=self.type.value,
                text=self.text
            )

    @dataclass(slots=True)
    class PhoneNumberButton(NewButtonABC):
        """
        Phone number buttons call the specified business phone number when tapped by the app user.
        Templates are limited to one phone number button.

        Example:
            >>> from pywa.types import NewTemplate
            >>> NewTemplate.PhoneNumberButton(title='Call Us', phone_number='12125552368')

        Attributes:
            title: Button text (Up to 25 characters, no placeholders allowed).
            phone_number: Alphanumeric string. Business phone number to be (display phone number)
             called when the user taps the button (Up to 20 characters, no placeholders allowed).
        """
        type: ButtonType = field(default=ButtonType.PHONE_NUMBER, init=False)
        title: str
        phone_number: int | str

        def to_dict(self, placeholder: None = None) -> dict[str, str]:
            return dict(type=self.type.value, text=self.title, phone_number=str(self.phone_number))

    @dataclass(slots=True)
    class UrlButton(NewButtonABC):
        """
        URL buttons load the specified URL in the device's default web browser when tapped by the app user.
        Templates are limited to two URL buttons.

        Example:
            >>> from pywa.types import NewTemplate
            >>> NewTemplate.UrlButton(
            ...     title='Log In',
            ...     url='https://x.com/login?email={john@example}'
            ... )

        Attributes:
            title: Button text (Up to 25 characters, supports 1 variable).
            url: URL to be loaded when the user taps the button (Up to 2000 characters, supports 1 placeholder, which
             be appended to the end of the URL).
        """
        type: ComponentType = field(default=ButtonType.URL, init=False)
        title: str
        url: str

        def to_dict(self, placeholder: tuple[str, str] = None) -> dict[str, str]:
            formatted_title, title_examples = (
                _get_examples_from_placeholders(self.title, *(placeholder if placeholder else ()))
            )
            formatted_url, url_examples = (
                _get_examples_from_placeholders(self.url, *(placeholder if placeholder else ()))
            )
            examples = title_examples + url_examples
            return dict(
                type=self.type.value,
                text=formatted_title,
                url=formatted_url,
                **(dict(example=examples if examples else {}))
            )

    @dataclass(slots=True)
    class QuickReplyButton(NewButtonABC):
        """
        Quick reply buttons are custom text-only buttons that immediately message you with the specified text string when
        tapped by the app user. A common use case-case is a button that allows your customer to easily opt-out of any
        marketing messages.

            - You will provide the callback data when you send the template.

        Templates are limited to 10 quick reply buttons. If using quick reply buttons with other buttons, buttons must be
        organized into two groups: quick reply buttons and non-quick reply buttons. If grouped incorrectly, the API will
        return an error indicating an invalid combination.

        Example:

            >>> from pywa.types import NewTemplate
            >>> NewTemplate.QuickReplyButton(text='Unsubscribe from Promos')
            >>> NewTemplate.QuickReplyButton(text='Unsubscribe from All')

        Attributes:
            text: The text to send when the user taps the button (Up to 25 characters, no placeholders allowed).
        """
        type: ComponentType = field(default=ButtonType.QUICK_REPLY, init=False)
        text: str

        def to_dict(self, placeholder: None = None) -> dict[str, str]:
            return dict(type=self.type.value, text=self.text)

    @dataclass(slots=True)
    class OTPButton(NewButtonABC):
        """
        Represents a button that can be used to send an OTP.

        Example for ONE_TAP:

            >>> from pywa.types import NewTemplate
            >>> NewTemplate.OTPButton(
            ...     otp_type=NewTemplate.OTPButton.OtpType.ONE_TAP,
            ...     title='Copy Code',
            ...     autofill_text='Autofill',
            ...     package_name='com.example.app',
            ...     signature_hash='1234567890ABCDEF1234567890ABCDEF12345678'
            ... )

        Example for COPY_CODE:

            >>> from pywa.types import NewTemplate
            >>> NewTemplate.OTPButton(
            ...     otp_type=NewTemplate.OTPButton.OtpType.COPY_CODE,
            ...     title='Copy Code'
            ... )


        Attributes:
            otp_type: Type of OTP to send. A copy code button copies the one-time password or code to the user's clipboard.
             The user can then manually switch to your app and paste the password or code into your app's interface. A
             one-tap autofill button automatically loads and passes your app the one-time password or code.
            title: Copy code button text. If omitted, the text will default to a pre-set value localized to the template's
             language. For example, ``Copy Code`` for English (US).
            autofill_text: One-tap autofill button text. If omitted, the text will default to a pre-set value localized to
                the template's language. For example, ``Autofill`` for English (US).
            package_name: Android package name of your app. Required if ``otp_type`` is ``OtpType.ONE_TAP``.
            signature_hash: Your app signing key hash. See `App Signing Key Hash
             <https://developers.facebook.com/docs/whatsapp/business-management-api/authentication-templates#app-signing-key-hash>`_
             for more information. Required if ``otp_type`` is ``OtpType.ONE_TAP``.
        """
        type: ComponentType = field(default=ButtonType.OTP, init=False)
        otp_type: OtpType
        title: str | None = None
        autofill_text: str | None = None
        package_name: str | None = None
        signature_hash: str | None = None

        class OtpType(utils.StrEnum):
            """The type of the button"""
            COPY_CODE = 'COPY_CODE'
            ONE_TAP = 'ONE_TAP'

        def __post_init__(self):
            if self.otp_type == self.OtpType.ONE_TAP and not (self.package_name and self.signature_hash):
                raise ValueError('`package_name` and `signature_hash` are required for ONE_TAP')

        def to_dict(self) -> dict[str, str | None]:
            base = dict(type=self.type.value, otp_type=self.otp_type.value, text=self.title)
            if self.otp_type == self.OtpType.ONE_TAP:
                base.update(
                    package_name=self.package_name,
                    signature_hash=self.signature_hash,
                    **(dict(autofill_text=self.autofill_text) if self.autofill_text else {})
                )
            return base


class ParamType(utils.StrEnum):
    TEXT = 'text'
    CURRENCY = 'currency'
    DATE_TIME = 'date_time'
    DOCUMENT = 'document'
    IMAGE = 'image'
    VIDEO = 'video'
    LOCATION = 'location'
    BUTTON = 'button'


class ButtonSubType(utils.StrEnum):
    QUICK_REPLY = 'quick_reply'
    URL = 'url'


class ComponentABC(abc.ABC):
    @property
    @abc.abstractmethod
    def type(self) -> ParamType: ...


@dataclass(slots=True)
class Template:
    """
    The template to send.

    The template message is basically a message that contains the values of the template placeholders.

    If in the template created with body that contains 3 variables, then the message must contain 3 values for the
    placeholders.

    >>> from pywa.types import Template as Temp
    >>> Temp(
    ...     name='buy_new_iphone_x',
    ...     language='en_US',
    ...     header=TextValue(value='15'),
    ...     body=[
    ...         Temp.TextValue(value='John Doe'),
    ...         Temp.TextValue(value='WA_IPHONE_15'),
    ...         Temp.TextValue(value='15%'),
    ...     ],
    ...     buttons=[
    ...         Temp.UrlButtonValue(value='iphone15'),
    ...         Temp.QuickReplyButtonData(data='unsubscribe_from_marketing_messages'),
    ...         Temp.QuickReplyButtonData(data='unsubscribe_from_all_messages'),
    ...     ],
    ... )

    Example for Authentication template:

    >>> from pywa.types import Template as Temp
    >>> Temp(
    ...     name='auth_with_otp',
    ...     language='en_US',
    ...     buttons=Temp.OTPButtonCode(code='123456'),
    ... )


    Attributes:
        name: The name of the template.
        language: The language of the template (See `Template language and locale code
            <https://developers.facebook.com/docs/whatsapp/business-management-api/message-templates/supported-languages>`_).
        body: The body of the template, which can include one or more text variables.
        header: The header of the template (required base on the template you are sending).
        buttons: The buttons to send with the template (required base on the template you are sending).
    """
    name: str
    language: str
    body: Iterable[TextValue | Currency | DateTime] | None = None
    header: TextValue | Document | Image | Video | Location | None = None
    buttons: Iterable[QuickReplyButtonData | UrlButtonValue] | OTPButtonCode | None = None

    def __post_init__(self):
        if isinstance(self.buttons, self.OTPButtonCode):
            if any((self.header, self.body)):
                raise ValueError('`body` and `header` are not allowed for AUTHENTICATION')
            self.body = (self.TextValue(value=self.buttons.code),)

    def to_dict(self, is_header_url: bool = False) -> dict[str, str | dict[str, str | tuple[dict[str, str], ...]]]:
        return dict(
            name=self.name,
            language=dict(code=self.language),
            components=tuple(comp for comp in (
                dict(
                    type=ComponentType.BODY.value,
                    parameters=tuple(component.to_dict() for component in self.body)
                ) if self.body else None,
                dict(
                    type=ComponentType.HEADER.value,
                    parameters=(self.header.to_dict(is_header_url),)
                ) if self.header else None,
                *((dict(
                    type=b.type.value,
                    sub_type=b.sub_type.value,
                    index=idx,
                    parameters=(b.to_dict(),)
                ) for idx, b in enumerate(self.buttons)) if self.buttons is not None else ())
            ) if comp is not None)
        )

    @dataclass(slots=True)
    class TextValue(ComponentABC):
        """
        Represents a value to variable in the template.

        Example:
            >>> from pywa.types import Template
            >>> Template.TextValue(var='John Doe')  # The template was created with 'Hello, {John}!'

        Attributes:
            value: The value to assign to the variable in the template.
        """
        type: ParamType = field(default=ParamType.TEXT, init=False)
        value: str

        def to_dict(self, is_url: None = None) -> dict[str, str]:
            return dict(type=self.type.value, text=self.value)

    @dataclass(slots=True)
    class Currency(ComponentABC):
        """
        Represents a currency variable.

        Attributes:
            fallback_value: Default text if localization fails.
            code: ISO 4217 currency code (e.g. USD, EUR, etc.).
            amount_1000: Amount multiplied by 1000.
        """
        type: ParamType = field(default=ParamType.CURRENCY, init=False)
        fallback_value: str
        code: str
        amount_1000: int

        def to_dict(self) -> dict[str, str]:
            return dict(
                type=self.type.value,
                currency=dict(
                    fallback_value=self.fallback_value,
                    code=self.code,
                    amount_1000=self.amount_1000
                )
            )

    @dataclass(slots=True)
    class DateTime(ComponentABC):
        """
        Represents a date time variable.

        Attributes:
            fallback_value: Default text if localization fails.
        """
        type: ParamType = field(default=ParamType.DATE_TIME, init=False)
        fallback_value: str

        def to_dict(self) -> dict[str, str]:
            return dict(
                type=self.type.value,
                date_time=dict(
                    fallback_value=self.fallback_value,
                )
            )

    @dataclass(slots=True)
    class Document(ComponentABC):
        """
        Represents a document.

        Attributes:
            document: The document to send (PDF only. either a media ID, URL, file path, bytes, or an open file object).
        """
        type: ParamType = field(default=ParamType.DOCUMENT, init=False)
        document: str | bytes | BinaryIO

        def to_dict(self, is_url: bool) -> dict[str, str]:
            return dict(type=self.type.value, document=dict(url=self.document) if is_url else dict(id=self.document))

    @dataclass(slots=True)
    class Image(ComponentABC):
        """
        Represents an image.

        Attributes:
            image: The image to send (either a media ID, URL, file path, bytes, or an open file object).
        """
        type: ParamType = field(default=ParamType.IMAGE, init=False)
        image: str | bytes | BinaryIO

        def to_dict(self, is_url: bool) -> dict[str, str]:
            return dict(type=self.type.value, image=dict(url=self.image) if is_url else dict(id=self.image))

    @dataclass(slots=True)
    class Video(ComponentABC):
        """
        Represents a video.

        Attributes:
            video: The video to send (either a media ID, URL, file path, bytes, or an open file object).
        """
        type: ParamType = field(default=ParamType.VIDEO, init=False)
        video: str | bytes | BinaryIO

        def to_dict(self, is_url: bool) -> dict[str, str]:
            return dict(type=self.type.value, video=dict(url=self.video) if is_url else dict(id=self.video))

    @dataclass(slots=True)
    class Location(ComponentABC):
        """
        Represents a location.

        Attributes:
            latitude: The latitude of the location.
            longitude: The longitude of the location.
            name: The name of the location.
            address: The address of the location.
        """
        type: ParamType = field(default=ParamType.LOCATION, init=False)
        latitude: float
        longitude: float
        name: str | None = None
        address: str | None = None

        def to_dict(self) -> dict[str, str]:
            return dict(
                type=self.type.value,
                location=dict(
                    latitude=self.latitude,
                    longitude=self.longitude,
                    **(dict(name=self.name) if self.name else {}),
                    **(dict(address=self.address) if self.address else {})
                )
            )

    @dataclass(slots=True)
    class QuickReplyButtonData(ComponentABC):
        """
        Represents a quick reply button.

        Attributes:
            data: The data to send when the user taps the button (you can listen for this data in the webhook).
        """
        type: ParamType = field(default=ParamType.BUTTON, init=False)
        sub_type: ButtonSubType = field(default=ButtonSubType.QUICK_REPLY, init=False)
        data: str

        def to_dict(self) -> dict[str, str]:
            return dict(type='payload', payload=self.data)

    @dataclass(slots=True)
    class UrlButtonValue(ComponentABC):
        """
        Represents a URL button variable.

        Example:
            >>> from pywa.types import Template
            >>> Template.UrlButtonValue(value='COUPON123')  # The template was created with 'https://example.com/shop/{COUPON12}'

        Attributes:
            value: The value to assign to the variable in the template (appended to the end of the URL).
        """
        type: ParamType = field(default=ParamType.BUTTON, init=False)
        sub_type: ButtonSubType = field(default=ButtonSubType.URL, init=False)
        value: str

        def to_dict(self) -> dict[str, str]:
            return dict(type='text', text=self.value)

    @dataclass(slots=True)
    class OTPButtonCode(ComponentABC):
        """
        Represents an OTP button variable.

        Example:
            >>> from pywa.types import Template
            >>> Template.OTPButtonCode(value='123456')

        Attributes:
            code: The code to copy or autofill when the user taps the button.
        """
        type: ParamType = field(default=ParamType.BUTTON, init=False)
        sub_type: ButtonSubType = field(default=ButtonSubType.URL, init=False)
        code: str

        def to_dict(self) -> dict[str, str]:
            return dict(type='text', text=self.code)

        def __iter__(self):
            yield self

        def __next__(self):
            return self
